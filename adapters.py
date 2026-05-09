"""
Adapter interfaces. Replace these classes with real API clients.
"""

import asyncio
import json
import time
from typing import Any, Dict, List, Optional
from pathlib import Path

import os
import aiohttp
import httpx
import fal_client
from api_secrets import KIE_API_KEY, MUAPIAPP_API_KEY, FAL_KEY

os.environ["FAL_KEY"] = FAL_KEY


def _format_muapi_error(status_code: int, body_text: str, context: str) -> str:
    """Normalize common MuAPI failures into actionable messages."""
    if status_code == 402:
        return (
            f"{context} failed: 402 {body_text}. "
            "MuAPI returned 'Insufficient credit balance'. "
            "This is a billing/quota issue, not an invalid key."
        )
    if status_code == 401:
        return (
            f"{context} failed: 401 {body_text}. "
            "Check that x-api-key is valid and active."
        )
    if status_code == 403:
        return (
            f"{context} failed: 403 {body_text}. "
            "Key is valid but lacks access to this model/endpoint."
        )
    return f"{context} failed: {status_code} {body_text}"


def _format_kie_error(status_code: int, body_text: str, context: str) -> str:
    if status_code == 401:
        return f"{context} failed: 401 {body_text}. Invalid/expired Kie API key."
    if status_code == 429:
        return f"{context} failed: 429 {body_text}. Kie rate limit exceeded."
    return f"{context} failed: {status_code} {body_text}"


class AsyncRateLimiter:
    """Simple in-process rate limiter for outbound provider calls."""

    def __init__(self, max_calls: int, period_seconds: float):
        self.max_calls = max_calls
        self.period_seconds = period_seconds
        self._timestamps: List[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            self._timestamps = [t for t in self._timestamps if now - t < self.period_seconds]
            if len(self._timestamps) >= self.max_calls:
                wait_for = self.period_seconds - (now - self._timestamps[0])
                if wait_for > 0:
                    await asyncio.sleep(wait_for)
                now = time.monotonic()
                self._timestamps = [t for t in self._timestamps if now - t < self.period_seconds]
            self._timestamps.append(time.monotonic())


# ---------------------------------------------------------
# UTILITY FUNCTIONS
# ---------------------------------------------------------

async def ensure_url(file_path_or_url: str) -> str:
    """
    Convert a local file path to a URL using fal_client, or return the URL as-is.
    Also handles problematic image formats by downloading, converting to PNG, and re-uploading.
    
    Args:
        file_path_or_url: Either a local file path or an existing URL
        
    Returns:
        A valid URL (either the original URL or uploaded file URL)
    """
    # Check if it's already a URL
    if file_path_or_url.startswith(('http://', 'https://')):
        # Check for problematic formats that might not be supported by Nano Banana
        problematic_formats = ['.avif', '.webp', '.svg']
        if any(file_path_or_url.lower().endswith(fmt) for fmt in problematic_formats):
            print(f"[ensure_url] Detected unsupported format, converting to PNG: {file_path_or_url}")
            try:
                # Download the image
                import tempfile
                from PIL import Image
                import io
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(file_path_or_url) as resp:
                        if resp.status == 200:
                            # Read image data
                            image_data = await resp.read()
                            
                            # Convert to PNG using PIL
                            print(f"[ensure_url] Converting image to PNG format...")
                            img = Image.open(io.BytesIO(image_data))
                            
                            # Convert RGBA to RGB if necessary (for compatibility)
                            if img.mode in ('RGBA', 'LA', 'P'):
                                # Create white background
                                background = Image.new('RGB', img.size, (255, 255, 255))
                                if img.mode == 'P':
                                    img = img.convert('RGBA')
                                background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                                img = background
                            elif img.mode != 'RGB':
                                img = img.convert('RGB')
                            
                            # Save as PNG to temp file
                            with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp:
                                img.save(tmp, format='PNG')
                                tmp_path = tmp.name
                            
                            # Re-upload through fal_client
                            print(f"[ensure_url] Re-uploading PNG through fal_client...")
                            new_url = await fal_client.upload_file_async(tmp_path)
                            
                            # Clean up temp file
                            import os
                            os.unlink(tmp_path)
                            
                            print(f"[ensure_url] Successfully converted and re-uploaded: {new_url}")
                            return new_url
                        else:
                            print(f"[ensure_url] Failed to download image (status {resp.status}), using original URL")
                            return file_path_or_url
            except Exception as e:
                print(f"[ensure_url] Error converting image: {e}, using original URL")
                import traceback
                traceback.print_exc()
                return file_path_or_url
        
        return file_path_or_url
    
    # Check if it's a valid local file
    file_path = Path(file_path_or_url)
    if file_path.exists() and file_path.is_file():
        # Upload the file and return the URL
        image_url = await fal_client.upload_file_async(str(file_path))
        return image_url
    
    # If neither URL nor valid file, raise an error
    raise ValueError(f"Invalid input: '{file_path_or_url}' is neither a valid URL nor an existing file path")


# ---------------------------------------------------------
# TEXT ADAPTER (Kie AI chat/completions)
# ---------------------------------------------------------

class TextAdapter:
    BASE_URL = "https://api.kie.ai"
    DEFAULT_MODEL = "gemini-2.5-flash"

    def __init__(self):
        self.api_key = KIE_API_KEY
        if not self.api_key:
            raise ValueError("KIE_API_KEY missing in api_secrets.py")
        self.model = os.getenv("KIE_TEXT_MODEL", self.DEFAULT_MODEL)
        self.rate_limiter = AsyncRateLimiter(max_calls=20, period_seconds=60.0)

    async def _single_generate(self, client: httpx.AsyncClient, prompt: str) -> str:
        await self.rate_limiter.acquire()
        url = f"{self.BASE_URL}/{self.model}/v1/chat/completions"
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(_format_kie_error(resp.status_code, resp.text, "Kie chat completion"))
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    async def generate(self, prompt: str, n: int = 1) -> List[str]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            tasks = [self._single_generate(client, prompt) for _ in range(n)]
            return await asyncio.gather(*tasks)


# ---------------------------------------------------------
# VISION ADAPTER (Kie AI multimodal chat/completions)
# ---------------------------------------------------------

class VisionAdapter:
    BASE_URL = "https://api.kie.ai"
    DEFAULT_MODEL = "gemini-2.5-flash"

    def __init__(self):
        self.api_key = KIE_API_KEY
        if not self.api_key:
            raise ValueError("KIE_API_KEY missing in api_secrets.py")
        self.model = os.getenv("KIE_VISION_MODEL", self.DEFAULT_MODEL)
        self.rate_limiter = AsyncRateLimiter(max_calls=12, period_seconds=60.0)

    async def analyze(self, prompt: str, image_url: str) -> dict:
        image_url = await ensure_url(image_url)
        await self.rate_limiter.acquire()

        url = f"{self.BASE_URL}/{self.model}/v1/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"Return strict JSON only. {prompt}"},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                }
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(url, json=payload, headers=headers)

        if resp.status_code != 200:
            raise RuntimeError(_format_kie_error(resp.status_code, resp.text, "Kie vision completion"))

        content = resp.json()["choices"][0]["message"]["content"]
        try:
            return json.loads(content)
        except Exception:
            return {"summary": content}


class ImageAdapter:
    BASE_URL = "https://api.kie.ai/api/v1/jobs"

    def __init__(self):
        self.api_key = KIE_API_KEY
        if not self.api_key:
            raise ValueError("KIE_API_KEY missing in api_secrets.py")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        self.rate_limiter = AsyncRateLimiter(max_calls=10, period_seconds=60.0)

    async def _create_task(self, payload: Dict) -> str:
        await self.rate_limiter.acquire()
        async with httpx.AsyncClient(timeout=60.0) as client:
            res = await client.post(f"{self.BASE_URL}/createTask", headers=self.headers, json=payload)
        if res.status_code != 200:
            raise Exception(_format_kie_error(res.status_code, res.text, "Kie createTask"))
        data = res.json()
        if not isinstance(data, dict):
            raise Exception("Kie createTask returned invalid response payload")
        api_code = data.get("code")
        api_msg = str(data.get("msg", "")).strip()
        if isinstance(api_code, int) and api_code != 200:
            raise Exception(f"Kie createTask failed with code {api_code}: {api_msg or 'unknown error'}")
        payload_data = data.get("data")
        if not isinstance(payload_data, dict):
            raise Exception(f"Kie createTask returned no task payload: code={api_code} msg={api_msg}")
        task_id = payload_data.get("taskId")
        if not task_id:
            raise Exception(f"Kie createTask missing taskId: {data}")
        return task_id

    async def _poll_task(self, task_id: str) -> Dict:
        url = f"{self.BASE_URL}/recordInfo?taskId={task_id}"
        async with httpx.AsyncClient(timeout=60.0) as client:
            while True:
                await self.rate_limiter.acquire()
                res = await client.get(url, headers=self.headers)
                if res.status_code != 200:
                    raise Exception(_format_kie_error(res.status_code, res.text, "Kie recordInfo"))
                data = res.json()
                state = data.get("data", {}).get("state")
                if state in {"success", "finished", "completed"}:
                    return data
                if state in {"failed", "error"}:
                    raise Exception(f"Kie task failed: {data}")
                await asyncio.sleep(1.0)

    def _extract_urls(self, task_result: Dict) -> List[str]:
        data = task_result.get("data", {})
        result_json = data.get("resultJson")
        parsed = {}
        if isinstance(result_json, str) and result_json:
            try:
                parsed = json.loads(result_json)
            except Exception:
                parsed = {}
        elif isinstance(result_json, dict):
            parsed = result_json

        for key in ("resultUrls", "result_urls", "images", "outputs"):
            value = parsed.get(key) if isinstance(parsed, dict) else None
            if isinstance(value, list) and value:
                urls = []
                for item in value:
                    if isinstance(item, str):
                        urls.append(item)
                    elif isinstance(item, dict):
                        url = item.get("url")
                        if url:
                            urls.append(url)
                if urls:
                    return urls
        return []

    def _size_to_aspect_ratio(self, size: tuple) -> str:
        width, height = size
        if width == height:
            return "1:1"
        return "16:9" if width > height else "9:16"

    async def generate_image(self, prompt: str, size=(1024, 1024)) -> List[str]:
        payload = {
            "model": os.getenv("KIE_IMAGE_MODEL", "google/nano-banana"),
            "callBackUrl": "",
            "input": {
                "prompt": prompt,
                "aspect_ratio": self._size_to_aspect_ratio(size),
            },
        }
        task_id = await self._create_task(payload)
        result = await self._poll_task(task_id)
        urls = self._extract_urls(result)
        if not urls:
            raise Exception(f"Kie image generation returned no URLs: {result}")
        return urls

    async def edit_image(self, image_url: str, instructions: str, aspect_ratio="1:1") -> str:
        image_url = await ensure_url(image_url)
        payload = {
            "model": os.getenv("KIE_IMAGE_EDIT_MODEL", "google/nano-banana-edit"),
            "callBackUrl": "",
            "input": {
                "prompt": instructions,
                "images_list": [image_url],
                "aspect_ratio": aspect_ratio,
            },
        }
        task_id = await self._create_task(payload)
        result = await self._poll_task(task_id)
        urls = self._extract_urls(result)
        if not urls:
            raise Exception(f"Kie image edit returned no URLs: {result}")
        return urls[0]

    async def generate_with_reference(self, prompt: str, reference_image_url: str, aspect_ratio="1:1") -> str:
        return await self.edit_image(reference_image_url, prompt, aspect_ratio)

class VideoAdapter:
    def __init__(self):
        self.api_key = KIE_API_KEY
        if not self.api_key:
            raise ValueError("KIE_API_KEY missing in api_secrets.py")
        self.base_url = "https://api.kie.ai/api/v1/jobs"
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        self.rate_limiter = AsyncRateLimiter(max_calls=8, period_seconds=60.0)

    async def _create_task(self, payload: Dict) -> str:
        await self.rate_limiter.acquire()
        async with httpx.AsyncClient(timeout=60.0) as client:
            res = await client.post(f"{self.base_url}/createTask", headers=self.headers, json=payload)
        if res.status_code != 200:
            raise Exception(_format_kie_error(res.status_code, res.text, "Kie video createTask"))
        data = res.json()
        if not isinstance(data, dict):
            raise Exception("Kie video createTask returned invalid response payload")
        api_code = data.get("code")
        api_msg = str(data.get("msg", "")).strip()
        if isinstance(api_code, int) and api_code != 200:
            raise Exception(f"Kie video createTask failed with code {api_code}: {api_msg or 'unknown error'}")
        payload_data = data.get("data")
        if not isinstance(payload_data, dict):
            raise Exception(f"Kie video createTask returned no task payload: code={api_code} msg={api_msg}")
        task_id = payload_data.get("taskId")
        if not task_id:
            raise Exception(f"Kie video createTask missing taskId: {data}")
        return task_id

    async def _poll_result(self, task_id: str) -> dict:
        """Poll Kie task status until finished."""
        url = f"{self.base_url}/recordInfo?taskId={task_id}"

        async with httpx.AsyncClient(timeout=60.0) as client:
            while True:
                await self.rate_limiter.acquire()
                res = await client.get(url, headers=self.headers)
                if res.status_code != 200:
                    raise Exception(_format_kie_error(res.status_code, res.text, "Kie video poll"))

                data = res.json()
                status = data.get("data", {}).get("state")

                if status in {"success", "finished", "completed"}:
                    print(f"[VideoAdapter] Request {task_id} completed.")
                    return data
                if status in {"failed", "error"}:
                    print(f"[VideoAdapter] Request {task_id} failed.")
                    raise Exception(f"Video generation failed: {data}")
                
                print(f"[VideoAdapter] Polling {task_id}: {status}...")

                await asyncio.sleep(1.0)

    def _extract_video_url(self, task_result: Dict) -> str:
        data = task_result.get("data", {})
        result_json = data.get("resultJson")
        parsed = {}
        if isinstance(result_json, str) and result_json:
            try:
                parsed = json.loads(result_json)
            except Exception:
                parsed = {}
        elif isinstance(result_json, dict):
            parsed = result_json

        for key in ("resultUrls", "result_urls", "outputs", "videos"):
            value = parsed.get(key) if isinstance(parsed, dict) else None
            if isinstance(value, list) and value:
                first = value[0]
                if isinstance(first, str):
                    return first
                if isinstance(first, dict) and first.get("url"):
                    return first["url"]
        raise Exception(f"Kie video task returned no video URL: {task_result}")

    # ----------------------------------------------------------
    # Main render() function — decides T2V or I2V automatically
    # ----------------------------------------------------------
    async def render(self, storyboard: Dict) -> str:
        """
        storyboard dict must contain:
        • prompt (required)
        • aspect_ratio (optional, for T2V only)
        • resolution
        • duration
        • image_url  (if present → I2V, else → T2V)
                     Can be a URL or local file path

        Returns: direct URL of generated video
        """
        # If image_url is provided, ensure it's a URL (upload if local file)
        if "image_url" in storyboard:
            storyboard["image_url"] = await ensure_url(storyboard["image_url"])
            return await self._generate_i2v(storyboard)
        else:
            return await self._generate_t2v(storyboard)

    # ----------------------------------------------------------
    # Text-to-Video (T2V)
    # ----------------------------------------------------------
    async def _generate_t2v(self, data: Dict) -> str:
        model_name = os.getenv("KIE_VIDEO_T2V_MODEL", "wan/2-7-text-to-video")
        input_payload: Dict[str, Any] = {
            "prompt": data["prompt"],
            "resolution": data.get("resolution", "720p"),
            "duration": data.get("duration", 5),
        }
        if not model_name.startswith("wan/"):
            input_payload["aspect_ratio"] = data.get("aspect_ratio", "16:9")

        payload = {
            "model": model_name,
            "callBackUrl": "",
            "input": input_payload,
        }
        print(f"[VideoAdapter] Generating T2V: {data['prompt']}")
        task_id = await self._create_task(payload)
        result = await self._poll_result(task_id)
        return self._extract_video_url(result)

    # ----------------------------------------------------------
    # Image-to-Video (I2V)
    # ----------------------------------------------------------
    async def _generate_i2v(self, data: Dict) -> str:
        model_name = os.getenv("KIE_VIDEO_I2V_MODEL", "wan/2-7-image-to-video")
        input_payload: Dict[str, Any] = {
            "prompt": data["prompt"],
            "resolution": data.get("resolution", "720p"),
            "duration": data.get("duration", 5),
        }
        if model_name.startswith("wan/"):
            input_payload["first_frame_url"] = data["image_url"]
        else:
            input_payload["image_url"] = data["image_url"]

        payload = {
            "model": model_name,
            "callBackUrl": "",
            "input": input_payload,
        }
        print(f"[VideoAdapter] Generating I2V: {data['prompt']}")
        task_id = await self._create_task(payload)
        result = await self._poll_result(task_id)
        return self._extract_video_url(result)


# ---------------------------------------------------------
# WEB SCRAPING ADAPTER
# ---------------------------------------------------------

# ---------------------------------------------------------
# WEB SCRAPING ADAPTER (Playwright)
# ---------------------------------------------------------

class WebScrapingAdapter:
    """
    Web scraping adapter using Playwright.
    Capable of rendering JavaScript, capturing screenshots, and extracting computed styles.
    """
    
    def __init__(self):
        self.user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    
    async def fetch_url(self, url: str, timeout: int = 30) -> Dict[str, any]:
        """
        Fetch content from a URL using Playwright.
        Extracts text, HTML, metadata, and visual assets (colors, fonts, images).
        """
        print(f"[WebScrapingAdapter] Fetching URL with Playwright: {url}")
        
        try:
            from playwright.async_api import async_playwright
            from bs4 import BeautifulSoup
        except ImportError:
            print("[WebScrapingAdapter] Playwright or BeautifulSoup not installed.")
            print("Please run: pip install playwright beautifulsoup4 && playwright install")
            return {"error": "Dependencies missing"}

        try:
            async with async_playwright() as p:
                # Launch browser
                try:
                    browser = await p.chromium.launch(headless=True)
                except Exception as e:
                    print(f"[WebScrapingAdapter] Failed to launch browser: {e}")
                    print("Try running: playwright install")
                    return {"error": "Browser launch failed"}

                context = await browser.new_context(
                    user_agent=self.user_agent,
                    viewport={"width": 1280, "height": 800}
                )
                page = await context.new_page()
                
                # Navigate
                try:
                    response = await page.goto(url, timeout=timeout*1000, wait_until="domcontentloaded")
                    status_code = response.status if response else 0
                    
                    # Wait for some dynamic content
                    await page.wait_for_timeout(2000)
                    
                    # Get content
                    content = await page.content()
                    title = await page.title()
                    
                    # Extract detailed assets via DOM evaluation
                    assets = await page.evaluate("""() => {
                        const getStyle = (el, prop) => getComputedStyle(el).getPropertyValue(prop);
                        
                        const colors = new Set();
                        const fonts = new Set();
                        
                        // Sample common elements for styles
                        const elements = document.querySelectorAll('body, h1, h2, h3, p, a, button, .btn, header, footer, div');
                        elements.forEach(el => {
                            const style = getComputedStyle(el);
                            if (style.color && style.color !== 'rgba(0, 0, 0, 0)') colors.add(style.color);
                            if (style.backgroundColor && style.backgroundColor !== 'rgba(0, 0, 0, 0)') colors.add(style.backgroundColor);
                            if (style.fontFamily) fonts.add(style.fontFamily);
                        });

                        // Images (filter small ones)
                        const images = Array.from(document.images)
                            .filter(img => img.naturalWidth > 50 && img.naturalHeight > 50)
                            .map(img => ({
                                src: img.src,
                                width: img.naturalWidth,
                                height: img.naturalHeight,
                                alt: img.alt
                            }));

                        // Links (for finding guidelines, social media)
                        const links = Array.from(document.links).map(a => ({
                            text: a.innerText.trim(),
                            href: a.href
                        }));

                        // Icons/Logos from head
                        const icons = Array.from(document.querySelectorAll('link[rel*="icon"], link[rel="apple-touch-icon"]'))
                            .map(l => l.href);
                            
                        // OpenGraph Image
                        const ogImage = document.querySelector('meta[property="og:image"]');
                        const ogImageUrl = ogImage ? ogImage.content : null;

                        return {
                            colors: Array.from(colors).slice(0, 50), // Limit to top 50
                            fonts: Array.from(fonts),
                            images: images.slice(0, 20), // Limit to top 20
                            links: links,
                            icons: icons,
                            og_image: ogImageUrl
                        };
                    }""")
                    
                    # Parse with BeautifulSoup for meta tags
                    soup = BeautifulSoup(content, 'html.parser')
                    
                    # Extract meta
                    metadata = {}
                    desc_tag = soup.find('meta', attrs={'name': 'description'})
                    if desc_tag: metadata['description'] = desc_tag.get('content', '')
                    
                    keywords_tag = soup.find('meta', attrs={'name': 'keywords'})
                    if keywords_tag: metadata['keywords'] = keywords_tag.get('content', '')
                    
                    # Clean text
                    for script in soup(["script", "style", "noscript"]):
                        script.decompose()
                    text = soup.get_text(separator=' ', strip=True)
                    
                    print(f"[WebScrapingAdapter] Successfully fetched {len(text)} chars")
                    
                    return {
                        "url": url,
                        "status_code": status_code,
                        "title": title,
                        "text": text,
                        "html": content,
                        "metadata": metadata,
                        "assets": assets  # New field with extracted assets
                    }
                    
                except Exception as e:
                    print(f"[WebScrapingAdapter] Navigation error: {e}")
                    return {
                        "url": url,
                        "status_code": 0,
                        "error": str(e),
                        "text": "",
                        "title": "",
                        "metadata": {},
                        "assets": {}
                    }
                finally:
                    await browser.close()
                    
        except Exception as e:
            print(f"[WebScrapingAdapter] Critical error: {e}")
            return {"error": str(e)}

    async def capture_screenshot(self, url: str, output_path: str = None) -> str:
        """
        Capture a screenshot of the website.
        Returns the path to the screenshot or a URL if uploaded.
        """
        print(f"[WebScrapingAdapter] Capturing screenshot: {url}")
        
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return None

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent=self.user_agent,
                    viewport={"width": 1280, "height": 800}
                )
                page = await context.new_page()
                
                await page.goto(url, wait_until="networkidle", timeout=30000)
                
                # Generate filename if not provided
                if not output_path:
                    import time
                    filename = f"screenshot_{int(time.time())}.png"
                    output_path = os.path.abspath(filename)
                
                await page.screenshot(path=output_path, full_page=False)
                print(f"[WebScrapingAdapter] Screenshot saved to {output_path}")
                
                await browser.close()
                
                # Upload to Fal for URL access if needed
                if os.environ.get("FAL_KEY"):
                    try:
                        image_url = await fal_client.upload_file_async(output_path)
                        print(f"[WebScrapingAdapter] Screenshot uploaded: {image_url}")
                        return image_url
                    except Exception as e:
                        print(f"[WebScrapingAdapter] Upload failed: {e}")
                        return output_path
                
                return output_path
                
        except Exception as e:
            print(f"[WebScrapingAdapter] Screenshot failed: {e}")
            return None

    async def search_and_fetch(self, query: str, num_results: int = 3) -> List[Dict[str, any]]:
        """Placeholder for search functionality."""
        print(f"[WebScrapingAdapter] Search not implemented.")
        return []
