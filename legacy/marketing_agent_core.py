#!/usr/bin/env python3
# marketing_agent_core.py
"""
Marketing Agent - Similar to Google's Pomelli
Creates on-brand marketing campaigns for businesses.

Key Features:
1. Business DNA Analysis - Analyzes website/content to understand brand identity
2. Campaign Idea Generation - Suggests tailored marketing campaigns
3. On-Brand Asset Creation - Generates social posts, banners, ads
4. Multi-Channel Support - Social media, web, email, ads
"""

import json
from typing import Dict, Any, List, Optional
from datetime import datetime
import sys
import os

# Add parent directory to path to import adapters
# sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from adapters import TextAdapter, ImageAdapter, VideoAdapter, VisionAdapter, WebScrapingAdapter
from adapters import TextAdapter, ImageAdapter, VideoAdapter, VisionAdapter, WebScrapingAdapter
from brand_analyzer import BrandAnalyzer
from campaign_generator import CampaignGenerator
from variation_generator import VariationGenerator


class MarketingAgent:
    """
    AI Marketing Agent inspired by Google's Pomelli.
    Helps businesses create on-brand marketing campaigns.
    """
    
    SYSTEM_PROMPT = """You are an expert AI marketing agent, similar to Google's Pomelli. You help businesses create on-brand marketing campaigns.

YOUR ROLE:
You are a "marketing department in a box" for small and medium businesses. You analyze their brand, suggest campaign ideas, and generate on-brand marketing assets.

YOUR CAPABILITIES (Tools you can call):
- research_web(url: str) → Analyzes business website to extract brand DNA (including logo)
- analyze_brand_dna(website_content: dict) → Creates comprehensive brand identity profile
- generate_campaign_ideas(brand_dna: dict, goal: str) → Suggests tailored marketing campaigns
- generate_image(prompt: str, reference_image_url: Optional[str]) → Creates marketing visuals
  * Can use ANY image as reference by passing reference_image_url parameter
  * AUTOMATICALLY uses brand logo as reference if available (when reference_image_url not provided)
  * Reference-based generation ensures brand consistency and visual coherence
  * Use reference images for: logo placement, style matching, product shots, brand elements
  * Examples: generate_image("Instagram post", reference_image_url="https://...product.jpg")
- generate_video(prompt: str, image_url: Optional[str], duration: int) → Creates video ads
- generate_copy(brief: str, num_variants: int) → Creates marketing copy and taglines
- generate_social_post(platform: str, campaign: dict) → Creates platform-specific posts
- generate_ad_creative(ad_type: str, campaign: dict) → Creates ad creatives
- generate_full_campaign(campaign_type: str, brief: str) → Creates a complete multi-asset campaign
- generate_variations(base_prompt: str, asset_type: str) → Creates design variations

YOUR WORKFLOW:
1. **Extract Business DNA**: Analyze the business website to understand:
   - Brand identity (tone of voice, personality)
   - Visual style (colors, fonts, imagery)
   - Target audience
   - Key products/services
   - Unique value proposition

2. **Understand Marketing Goals**: Ask about:
   - Campaign objective (awareness, leads, sales, engagement)
   - Target audience specifics
   - Channels (social media, web, email, ads)
   - Timeline and budget constraints

3. **Generate Campaign Ideas**: Suggest 3-5 tailored campaigns based on:
   - Brand DNA
   - Marketing goals
   - Industry best practices
   - Current trends

4. **Create On-Brand Assets**: Generate:
   - Social media posts (Instagram, Facebook, LinkedIn, Twitter)
   - Web banners and hero images
   - Ad creatives (display ads, video ads)
   - Email headers and graphics
   - All assets maintain brand consistency

5. **Iterate and Refine**: Based on feedback:
   - Adjust messaging and tone
   - Refine visual style
   - Create variations
   - Optimize for different platforms

OUTPUT FORMAT:
{
  "thinking": "Internal reasoning about the marketing strategy...",
  "message": "Conversational response to user...",
  "tool_calls": [...],
  "suggestions": ["Next steps or alternative approaches..."],
  "needs_user_input": true/false
}

CRITICAL RULES:
1. **Brand DNA First**: ALWAYS analyze the business website before suggesting campaigns
2. **On-Brand Consistency**: All assets must match the extracted brand identity (colors, fonts, tone)
3. **Goal-Oriented**: Every campaign should clearly support the stated marketing objective
4. **Platform-Specific**: Tailor content for each platform (Instagram vs LinkedIn have different tones)
5. **Actionable**: Provide clear CTAs and next steps in all marketing materials
6. **STOP After Generating**: After creating assets, set needs_user_input: true and wait for feedback
7. **Logical Task Ordering**: Extract DNA → Understand goals → Suggest campaigns → Create assets

BRAND DNA STRUCTURE:
{
  "brand_name": "string",
  "industry": "string",
  "tone_of_voice": ["professional", "friendly", "innovative", etc.],
  "visual_style": {
    "colors": ["#hex1", "#hex2"],
    "fonts": ["font1", "font2"],
    "imagery_style": "description"
  },
  "target_audience": "description",
  "value_proposition": "string",
  "key_products": ["product1", "product2"],
  "brand_personality": ["trait1", "trait2"]
}

CAMPAIGN TYPES:
- Product Launch: Introduce new product/service
- Brand Awareness: Increase visibility and recognition
- Lead Generation: Capture potential customer information
- Engagement: Build community and interaction
- Sales/Promotion: Drive immediate purchases
- Thought Leadership: Establish expertise and authority

EXAMPLE INTERACTION:
User: "Create a marketing campaign for https://example.com"

Turn 1 (Extract Brand DNA):
{
  "thinking": "I need to understand this business first. I'll analyze their website to extract brand DNA.",
  "tool_calls": [{"tool": "research_web", "params": {"url": "https://example.com"}}],
  "message": "I'm analyzing your website to understand your brand identity...",
  "needs_user_input": false
}

Turn 2 (Present DNA & Ask Goals):
{
  "thinking": "I've extracted the brand DNA. Now I should present it and ask about their marketing goals.",
  "message": "I've analyzed your brand! Here's what I found:\\n\\n**Brand DNA:**\\n- Tone: Professional yet approachable\\n- Colors: Blue (#0066CC) and White\\n- Audience: Tech-savvy professionals\\n\\nWhat's your marketing goal for this campaign?\\n1. Increase brand awareness\\n2. Generate leads\\n3. Drive sales\\n4. Build engagement",
  "needs_user_input": true
}

Turn 3 (Generate Campaign Ideas):
{
  "thinking": "User wants to generate leads. I'll suggest 3 campaigns tailored to their brand DNA.",
  "message": "Here are 3 lead generation campaigns for you:\\n\\n**Campaign 1: Free Tool Giveaway**\\n- Offer a free calculator/template\\n- Capture emails for download\\n- Follow-up nurture sequence\\n\\n**Campaign 2: Webinar Series**\\n- Educational content on industry topics\\n- Registration required\\n- Post-webinar consultation offers\\n\\n**Campaign 3: Case Study Showcase**\\n- Highlight customer success stories\\n- Downloadable PDF with email gate\\n- Social proof for credibility\\n\\nWhich campaign resonates with you?",
  "needs_user_input": true
}

Turn 4 (Create Assets):
{
  "thinking": "User chose Campaign 1. I'll create social posts, web banner, and email header for the free tool giveaway.",
  "tool_calls": [
    {"tool": "generate_social_post", "params": {"platform": "linkedin", "campaign": {...}}},
    {"tool": "generate_image", "params": {"prompt": "Web banner for free tool giveaway..."}},
    {"tool": "generate_copy", "params": {"brief": "Email subject lines for tool giveaway", "num_variants": 3}}
  ],
  "message": "Creating your campaign assets...",
  "needs_user_input": false
}

Turn 5 (Present Assets & Wait):
{
  "thinking": "I've created all the assets. Now I should present them and wait for feedback.",
  "message": "Here are your campaign assets! 🎯\\n\\n**LinkedIn Post:** [image]\\n**Web Banner:** [image]\\n**Email Subject Lines:**\\n1. Get Your Free [Tool Name] - No Credit Card Required\\n2. Boost Your [Outcome] with Our Free Tool\\n3. Limited Time: Free [Tool Name] for Professionals\\n\\nWhat would you like to adjust?",
  "needs_user_input": true
}

YOUR PERSONALITY:
- Strategic and data-driven, like a marketing director
- Creative and trend-aware
- Business-focused (ROI, conversions, metrics)
- Collaborative and iterative
- Clear and actionable

Begin every conversation with energy and marketing expertise!
"""

    def __init__(self):
        """Initialize the marketing agent with tools and state."""
        # Initialize tool adapters
        self.text_adapter = TextAdapter()
        self.image_adapter = ImageAdapter()
        self.video_adapter = VideoAdapter()
        self.vision_adapter = VisionAdapter()
        self.research_adapter = WebScrapingAdapter()
        
        # Initialize enhanced brand analyzer
        self.brand_analyzer = BrandAnalyzer()
        
        # Initialize generators
        self.campaign_generator = CampaignGenerator(self)
        self.variation_generator = VariationGenerator(self)
        
        # Marketing state
        self.conversation_history: List[Dict[str, str]] = []
        self.brand_dna: Optional[Dict[str, Any]] = None
        self.current_campaign: Optional[Dict[str, Any]] = None
        self.generated_assets: List[Dict[str, Any]] = []
        
        print(f"[MarketingAgent] Initialized - Ready to create marketing campaigns!")
        print(f"  ✅ Enhanced Brand DNA Analysis (Visual + Text)")
        print(f"  ✅ Campaign Idea Generation")
        print(f"  ✅ On-Brand Asset Creation")
        print(f"  ✅ Multi-Channel Support")
    
    async def process_message(self, user_message: str) -> Dict[str, Any]:
        """
        Main entry point: process a user message through the marketing workflow.
        
        Args:
            user_message: The user's input message
            
        Returns:
            Agent response with thinking, message, assets, and suggestions
        """
        print(f"\n[MarketingAgent] Processing message: {user_message[:60]}...")
        
        # Add user message to history
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })
        
        # Multi-turn reasoning loop
        max_iterations = 5
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            print(f"\n[MarketingAgent] Reasoning iteration {iteration}...")
            
            # Get agent decision
            decision = await self._get_agent_decision(user_message)
            
            # Execute tool calls if any
            if decision.get("tool_calls"):
                print(f"[MarketingAgent] Executing {len(decision['tool_calls'])} tool(s)...")
                execution_results = await self._execute_tools(decision["tool_calls"])
            else:
                execution_results = []
            
            # Check if agent needs user input
            if decision.get("needs_user_input", True):
                print(f"[MarketingAgent] Agent requests user input, stopping iteration")
                break
            
            # Continue to next iteration
            print(f"[MarketingAgent] Continuing to next iteration...")
        
        # Formulate final response
        response = self._formulate_response(decision, execution_results)
        
        # Add agent response to history
        self.conversation_history.append({
            "role": "assistant",
            "content": decision.get("message", "")
        })
        
        print(f"[MarketingAgent] Response ready with {len(response.get('generated_assets', []))} asset(s)")
        print(f"[MarketingAgent] Completed in {iteration} reasoning iteration(s)")
        
        return response
    
    async def _get_agent_decision(self, user_message: str) -> Dict[str, Any]:
        """Get the agent's decision based on context and user message."""
        
        # Build context
        context = self._build_context()
        
        # Build prompt
        prompt = f"""{self.SYSTEM_PROMPT}

## CURRENT CONTEXT
{context}

## USER'S LATEST MESSAGE
{user_message}

## YOUR TASK
Based on the conversation history and context, decide what to do next.
Think strategically about the marketing goals, show your reasoning, and respond professionally.
Return your response as JSON following the specified output format.

Remember:
- Extract Brand DNA first if analyzing a new business
- Suggest campaigns aligned with business goals
- Create on-brand assets that match the brand DNA
- Be strategic and ROI-focused
- STOP after generating assets and wait for feedback
"""
        
        print(f"[MarketingAgent] Agent is thinking...")
        
        try:
            responses = await self.text_adapter.generate(prompt, n=1)
            response_text = responses[0]
            
            # Clean markdown
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            
            decision = json.loads(response_text)
            
            return decision
            
        except json.JSONDecodeError as e:
            print(f"[MarketingAgent] JSON parse error: {e}")
            return {
                "thinking": "Processing your marketing request...",
                "message": "I'd be happy to help with your marketing campaign. Could you provide more details about your business and goals?",
                "tool_calls": [],
                "suggestions": [],
                "needs_user_input": True
            }
        except Exception as e:
            print(f"[MarketingAgent] Error: {e}")
            return {
                "thinking": "Encountered an issue...",
                "message": "Let me help you create an effective marketing campaign. What's your business website or tell me about your brand?",
                "tool_calls": [],
                "suggestions": [],
                "needs_user_input": True
            }
    
    def _build_context(self) -> str:
        """Build context string from conversation history and state."""
        
        context_parts = []
        
        # Recent conversation
        if self.conversation_history:
            recent = self.conversation_history[-6:]  # Last 3 exchanges
            conv_text = "\n".join([
                f"{'User' if msg['role'] == 'user' else 'You'}: {msg['content'][:200]}..."
                for msg in recent
            ])
            context_parts.append(f"## Recent Conversation\n{conv_text}")
        
        # Brand DNA
        if self.brand_dna:
            context_parts.append(f"## Brand DNA\n{json.dumps(self.brand_dna, indent=2)}")
        
        # Current Campaign
        if self.current_campaign:
            context_parts.append(f"## Current Campaign\n{json.dumps(self.current_campaign, indent=2)}")
        
        # Generated Assets
        if self.generated_assets:
            assets_summary = "\n".join([
                f"{i+1}. {asset['type']}: {asset.get('url', 'N/A')} (created: {asset.get('timestamp', 'N/A')})"
                for i, asset in enumerate(self.generated_assets[-10:])
            ])
            context_parts.append(f"## Generated Assets (Current Session)\n{assets_summary}")
        
        return "\n\n".join(context_parts) if context_parts else "No previous context."
    
    async def _execute_tools(self, tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Execute the requested tool calls."""
        
        results = []
        
        for call in tool_calls:
            tool_name = call.get("tool")
            params = call.get("params", {})
            
            print(f"[MarketingAgent] Executing {tool_name}...")
            
            try:
                if tool_name == "research_web":
                    url = params.get("url", "")
                    
                    # Use enhanced brand analyzer for comprehensive analysis
                    self.brand_dna = await self.brand_analyzer.analyze_website(url)
                    
                    result = {
                        "tool": tool_name,
                        "success": True,
                        "result": {"type": "brand_dna", "data": self.brand_dna}
                    }
                
                elif tool_name == "generate_image":
                    prompt = params.get("prompt", "")
                    reference_image_url = params.get("reference_image_url")
                    
                    # Auto-detect logo from brand DNA if not explicitly provided
                    # This provides smart defaults while allowing explicit override
                    if not reference_image_url and self.brand_dna:
                        reference_image_url = self._extract_logo_url(self.brand_dna)
                        if reference_image_url:
                            print(f"[MarketingAgent] Auto-detected brand logo for reference: {reference_image_url}")
                    elif reference_image_url:
                        print(f"[MarketingAgent] Using explicit reference image: {reference_image_url}")
                    
                    if reference_image_url:
                        # Use Nano Banana Edit for reference-based generation
                        print(f"[MarketingAgent] Generating image WITH reference (brand-consistent)")
                        url = await self.image_adapter.generate_with_reference(prompt, reference_image_url)
                    else:
                        # Use Nano Banana for text-to-image
                        print(f"[MarketingAgent] Generating image WITHOUT reference (text-only)")
                        urls = await self.image_adapter.generate_image(prompt)
                        url = urls[0] if urls else None
                    
                    asset = {
                        "type": "marketing_image",
                        "url": url,
                        "prompt": prompt,
                        "reference_image": reference_image_url,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    self.generated_assets.append(asset)
                    
                    result = {
                        "tool": tool_name,
                        "success": True,
                        "result": {"type": "image", "url": url}
                    }
                
                elif tool_name == "generate_video":
                    prompt = params.get("prompt", "")
                    image_url = params.get("image_url")
                    duration = params.get("duration", 5)
                    
                    url = await self.video_adapter.render({
                        "prompt": prompt,
                        "image_url": image_url,
                        "duration": duration
                    })
                    
                    asset = {
                        "type": "marketing_video",
                        "url": url,
                        "prompt": prompt,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    self.generated_assets.append(asset)
                    
                    result = {
                        "tool": tool_name,
                        "success": True,
                        "result": {"type": "video", "url": url}
                    }
                
                elif tool_name == "generate_copy":
                    brief = params.get("brief", "")
                    num_variants = params.get("num_variants", 3)
                    
                    # Generate copy variants
                    copy_variants = await self._generate_marketing_copy(brief, num_variants)
                    
                    result = {
                        "tool": tool_name,
                        "success": True,
                        "result": {"type": "copy", "variants": copy_variants}
                    }
                
                elif tool_name == "generate_social_post":
                    platform = params.get("platform", "instagram")
                    campaign = params.get("campaign", {})
                    
                    post = await self._generate_social_post(platform, campaign)
                    
                    result = {
                        "tool": tool_name,
                        "success": True,
                        "result": {"type": "social_post", "data": post}
                    }
                
                elif tool_name == "generate_full_campaign":
                    campaign_type = params.get("campaign_type", "social_media")
                    brief = params.get("brief", "")
                    
                    # Use CampaignGenerator
                    campaign_results = await self.campaign_generator.generate_campaign(
                        campaign_type=campaign_type,
                        campaign_brief=brief,
                        brand_guidelines=self.brand_dna if self.brand_dna else {}
                    )
                    
                    result = {
                        "tool": tool_name,
                        "success": True,
                        "result": {"type": "campaign", "data": campaign_results}
                    }

                elif tool_name == "generate_variations":
                    base_prompt = params.get("base_prompt", "")
                    asset_type = params.get("asset_type", "image")
                    num_variations = params.get("num_variations", 3)
                    strategy = params.get("strategy", "style")
                    
                    # Use VariationGenerator
                    variations = await self.variation_generator.generate_variations(
                        base_prompt=base_prompt,
                        asset_type=asset_type,
                        num_variations=num_variations,
                        strategy=strategy,
                        brand_guidelines=self.brand_dna.get("visual_style", {}) if self.brand_dna else {}
                    )
                    
                    result = {
                        "tool": tool_name,
                        "success": True,
                        "result": {"type": "variations", "data": variations}
                    }
                
                else:
                    result = {
                        "tool": tool_name,
                        "success": False,
                        "result": {"type": "error", "message": f"Unknown tool: {tool_name}"}
                    }
                
                results.append(result)
                
            except Exception as e:
                print(f"[MarketingAgent] Tool execution error ({tool_name}): {e}")
                results.append({
                    "tool": tool_name,
                    "success": False,
                    "result": {"type": "error", "message": str(e)}
                })
        
        return results
    
    async def _extract_brand_dna(self, website_content: Dict[str, Any]) -> Dict[str, Any]:
        """Extract brand DNA from website content using AI analysis."""
        
        print("[MarketingAgent] Extracting Brand DNA...")
        
        prompt = f"""Analyze this website content and extract the brand DNA:

Website Title: {website_content.get('title', 'N/A')}
Content: {website_content.get('text', '')[:2000]}

Extract and return as JSON:
{{
  "brand_name": "string",
  "industry": "string",
  "tone_of_voice": ["trait1", "trait2"],
  "visual_style": {{
    "colors": ["#hex1", "#hex2"],
    "fonts": ["font1", "font2"],
    "imagery_style": "description"
  }},
  "target_audience": "description",
  "value_proposition": "string",
  "key_products": ["product1", "product2"],
  "brand_personality": ["trait1", "trait2"]
}}

Be specific and actionable."""

        try:
            responses = await self.text_adapter.generate(prompt, n=1)
            response_text = responses[0]
            
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            
            brand_dna = json.loads(response_text)
            print(f"[MarketingAgent] ✅ Brand DNA extracted for {brand_dna.get('brand_name', 'Unknown')}")
            
            return brand_dna
            
        except:
            # Fallback brand DNA
            return {
                "brand_name": website_content.get('title', 'Business'),
                "industry": "General",
                "tone_of_voice": ["professional", "friendly"],
                "visual_style": {
                    "colors": ["#0066CC", "#FFFFFF"],
                    "fonts": ["Sans-serif"],
                    "imagery_style": "Clean and modern"
                },
                "target_audience": "General audience",
                "value_proposition": "Quality service",
                "key_products": [],
                "brand_personality": ["trustworthy", "innovative"]
            }
    
    async def _generate_marketing_copy(self, brief: str, num_variants: int) -> List[str]:
        """Generate marketing copy variants."""
        
        prompt = f"""Create {num_variants} marketing copy variants for:

{brief}

Brand DNA: {json.dumps(self.brand_dna, indent=2) if self.brand_dna else 'Professional and engaging'}

Requirements:
- Match the brand tone of voice
- Include clear CTAs
- Be concise and impactful
- Optimize for conversions

Return as JSON array of strings."""

        try:
            responses = await self.text_adapter.generate(prompt, n=1)
            response_text = responses[0]
            
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            
            variants = json.loads(response_text)
            return variants if isinstance(variants, list) else [response_text]
            
        except:
            return [f"Variant {i+1}: {brief}" for i in range(num_variants)]
    
    async def _generate_social_post(self, platform: str, campaign: Dict[str, Any]) -> Dict[str, Any]:
        """Generate platform-specific social media post."""
        
        # Platform-specific requirements
        platform_specs = {
            "instagram": {"max_chars": 2200, "hashtags": 30, "tone": "visual and engaging"},
            "linkedin": {"max_chars": 3000, "hashtags": 5, "tone": "professional and insightful"},
            "twitter": {"max_chars": 280, "hashtags": 2, "tone": "concise and punchy"},
            "facebook": {"max_chars": 63206, "hashtags": 3, "tone": "conversational and friendly"}
        }
        
        specs = platform_specs.get(platform, platform_specs["instagram"])
        
        # Generate post content
        prompt = f"""Create a {platform} post for this campaign:

Campaign: {json.dumps(campaign, indent=2)}
Brand DNA: {json.dumps(self.brand_dna, indent=2) if self.brand_dna else 'Professional'}

Platform Requirements:
- Max characters: {specs['max_chars']}
- Tone: {specs['tone']}
- Include {specs['hashtags']} relevant hashtags

Return as JSON:
{{
  "caption": "string",
  "hashtags": ["tag1", "tag2"],
  "cta": "string",
  "image_prompt": "description for image generation"
}}"""

        try:
            responses = await self.text_adapter.generate(prompt, n=1)
            response_text = responses[0]
            
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            
            post_data = json.loads(response_text)
            
            # Generate image for the post
            if post_data.get("image_prompt"):
                urls = await self.image_adapter.generate_image(post_data["image_prompt"])
                post_data["image_url"] = urls[0] if urls else None
                
                # Store as asset
                self.generated_assets.append({
                    "type": f"{platform}_post",
                    "url": post_data["image_url"],
                    "caption": post_data["caption"],
                    "timestamp": datetime.utcnow().isoformat()
                })
            
            return post_data
            
        except Exception as e:
            print(f"[MarketingAgent] Social post generation error: {e}")
            return {
                "caption": f"Check out our latest {campaign.get('name', 'campaign')}!",
                "hashtags": ["marketing", "business"],
                "cta": "Learn more",
                "image_url": None
            }
    
    def _formulate_response(
        self,
        decision: Dict[str, Any],
        execution_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Formulate the final response to the user."""
        
        response = {
            "agent_response": decision.get("message", ""),
            "thinking_process": decision.get("thinking", ""),
            "generated_assets": [],
            "suggestions": decision.get("suggestions", []),
            "needs_user_input": decision.get("needs_user_input", False)
        }
        
        # Add execution results to response
        for exec_result in execution_results:
            if exec_result["success"]:
                result_data = exec_result["result"]
                
                if result_data["type"] in ["image", "video", "social_post"]:
                    response["generated_assets"].append(result_data)
                elif result_data["type"] == "copy":
                    if "copy_variants" not in response:
                        response["copy_variants"] = []
                    response["copy_variants"].extend(result_data.get("variants", []))
                elif result_data["type"] == "brand_dna":
                    response["brand_dna"] = result_data["data"]
        
        return response
    
    def get_brand_dna(self) -> Optional[Dict[str, Any]]:
        """Get the current brand DNA."""
        return self.brand_dna
    
    def get_generated_assets(self) -> List[Dict[str, Any]]:
        """Get all generated marketing assets."""
        return self.generated_assets


    def update_brand_memory(self, brand_guidelines: Dict[str, Any]):
        """Update brand memory with new guidelines."""
        if not self.brand_dna:
            self.brand_dna = {}
        
        if "visual_style" not in self.brand_dna:
            self.brand_dna["visual_style"] = {}
            
        self.brand_dna["visual_style"].update(brand_guidelines)
        print(f"[MarketingAgent] Updated brand memory with new guidelines")

    def _extract_logo_url(self, brand_dna: Dict[str, Any]) -> Optional[str]:
        """
        Extract logo URL from brand DNA.
        Checks multiple possible locations.
        
        Args:
            brand_dna: Brand DNA dictionary
            
        Returns:
            Logo URL or None
        """
        if not isinstance(brand_dna, dict):
            return None
        
        # Check visual_style.logo.url
        visual_style = brand_dna.get("visual_style", {})
        if isinstance(visual_style, dict):
            logo_data = visual_style.get("logo", {})
            if isinstance(logo_data, dict) and logo_data.get("url"):
                return logo_data["url"]
        
        # Check assets.logo_url
        assets = brand_dna.get("assets", {})
        if isinstance(assets, dict) and assets.get("logo_url"):
            return assets["logo_url"]
        
        # Check logo_url directly
        if brand_dna.get("logo_url"):
            return brand_dna["logo_url"]
        
        return None
