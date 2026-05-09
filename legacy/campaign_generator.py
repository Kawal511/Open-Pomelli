#!/usr/bin/env python3
# campaign_generator.py
"""
Complete Campaign Generator - Creates multi-asset campaigns
Generates coordinated brand campaigns with multiple asset types.
"""

import json
from typing import Dict, Any, List, Optional
from datetime import datetime


class CampaignGenerator:
    """
    Generates complete, multi-asset campaigns with brand consistency.
    """
    
    CAMPAIGN_TYPES = {
        "brand_identity": {
            "deliverables": ["logo", "color_palette", "typography", "business_card", "letterhead", "social_media_kit"],
            "description": "Complete brand identity package"
        },
        "product_launch": {
            "deliverables": ["product_mockup", "hero_image", "social_posts", "video_ad", "email_header"],
            "description": "Product launch campaign"
        },
        "social_media": {
            "deliverables": ["instagram_post", "instagram_story", "facebook_post", "twitter_header", "linkedin_post"],
            "description": "Social media campaign"
        },
        "website": {
            "deliverables": ["hero_section", "feature_images", "about_image", "cta_banner", "favicon"],
            "description": "Website design package"
        },
        "event": {
            "deliverables": ["event_poster", "social_announcement", "ticket_design", "banner", "program_cover"],
            "description": "Event marketing campaign"
        }
    }
    
    def __init__(self, agent):
        """
        Initialize campaign generator.
        
        Args:
            agent: Reference to the main MarketingAgent instance
        """
        self.agent = agent
        print("[CampaignGenerator] Initialized")
    
    async def generate_campaign(
        self,
        campaign_type: str,
        campaign_brief: str,
        brand_guidelines: Dict[str, Any],
        custom_deliverables: List[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a complete campaign with multiple coordinated assets.
        
        Args:
            campaign_type: Type of campaign (brand_identity, product_launch, etc.)
            campaign_brief: Description of the campaign
            brand_guidelines: Brand guidelines to follow
            custom_deliverables: Optional custom list of deliverables
            
        Returns:
            Campaign results with all generated assets
        """
        print(f"\n[CampaignGenerator] 🚀 Starting {campaign_type} campaign generation")
        print(f"[CampaignGenerator] Brief: {campaign_brief[:100]}...")
        
        # Get deliverables list
        if custom_deliverables:
            deliverables = custom_deliverables
        elif campaign_type in self.CAMPAIGN_TYPES:
            deliverables = self.CAMPAIGN_TYPES[campaign_type]["deliverables"]
        else:
            deliverables = ["image", "social_post", "banner"]
        
        print(f"[CampaignGenerator] Deliverables: {', '.join(deliverables)}")
        
        # Initialize campaign results
        campaign_results = {
            "campaign_type": campaign_type,
            "campaign_brief": campaign_brief,
            "brand_guidelines": brand_guidelines,
            "deliverables": deliverables,
            "assets": [],
            "started_at": datetime.utcnow().isoformat(),
            "status": "in_progress"
        }
        
        # Update brand memory with guidelines
        self.agent.update_brand_memory(brand_guidelines)
        
        # Generate each deliverable
        for idx, deliverable in enumerate(deliverables, 1):
            print(f"\n[CampaignGenerator] 📦 Generating {deliverable} ({idx}/{len(deliverables)})")
            
            try:
                # Generate asset with brand consistency
                asset = await self._generate_deliverable(
                    deliverable_type=deliverable,
                    campaign_brief=campaign_brief,
                    brand_guidelines=brand_guidelines,
                    previous_assets=campaign_results["assets"]
                )
                
                campaign_results["assets"].append(asset)
                print(f"[CampaignGenerator] ✅ {deliverable} completed")
                
            except Exception as e:
                print(f"[CampaignGenerator] ⚠️ Failed to generate {deliverable}: {e}")
                campaign_results["assets"].append({
                    "type": deliverable,
                    "status": "failed",
                    "error": str(e)
                })
        
        # Finalize campaign
        campaign_results["completed_at"] = datetime.utcnow().isoformat()
        campaign_results["status"] = "completed"
        campaign_results["success_count"] = len([a for a in campaign_results["assets"] if a.get("status") != "failed"])
        
        print(f"\n[CampaignGenerator] 🎉 Campaign complete! {campaign_results['success_count']}/{len(deliverables)} assets generated")
        
        return campaign_results
    
    async def _generate_deliverable(
        self,
        deliverable_type: str,
        campaign_brief: str,
        brand_guidelines: Dict[str, Any],
        previous_assets: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Generate a single deliverable with brand consistency.
        
        Args:
            deliverable_type: Type of deliverable to generate
            campaign_brief: Overall campaign brief
            brand_guidelines: Brand guidelines
            previous_assets: Previously generated assets for consistency
            
        Returns:
            Generated asset information
        """
        # Build context-aware prompt
        prompt = self._build_deliverable_prompt(
            deliverable_type=deliverable_type,
            campaign_brief=campaign_brief,
            brand_guidelines=brand_guidelines,
            previous_assets=previous_assets
        )
        
        # Determine asset dimensions based on type
        size = self._get_asset_dimensions(deliverable_type)
        
        # Extract reference image (logo or other brand asset)
        reference_image_url = self._get_reference_image(brand_guidelines, deliverable_type)
        
        # Generate the asset
        if deliverable_type in ["video_ad", "video"]:
            # Generate video
            url = await self.agent.video_adapter.render({
                "prompt": prompt,
                "duration": 5,
                "resolution": "720p",
                "aspect_ratio": "16:9"
            })
            
            asset = {
                "type": deliverable_type,
                "url": url,
                "prompt": prompt,
                "dimensions": "1280x720",
                "format": "video",
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            # Generate image with or without reference
            if reference_image_url and deliverable_type != "logo":
                # Use reference-based generation for brand consistency
                print(f"[CampaignGenerator] Using reference image: {reference_image_url}")
                url = await self.agent.image_adapter.generate_with_reference(
                    prompt=prompt,
                    reference_image_url=reference_image_url,
                    aspect_ratio=self._size_to_aspect_ratio(size)
                )
            else:
                # Use standard text-to-image generation
                urls = await self.agent.image_adapter.generate_image(prompt, size=size)
                url = urls[0] if urls else None
            
            asset = {
                "type": deliverable_type,
                "url": url,
                "prompt": prompt,
                "dimensions": f"{size[0]}x{size[1]}",
                "format": "image",
                "reference_image": reference_image_url if reference_image_url else None,
                "timestamp": datetime.utcnow().isoformat()
            }
        
        # Store in agent's asset list
        self.agent.generated_assets.append(asset)
        
        return asset
    
    def _build_deliverable_prompt(
        self,
        deliverable_type: str,
        campaign_brief: str,
        brand_guidelines: Dict[str, Any],
        previous_assets: List[Dict[str, Any]]
    ) -> str:
        """Build a context-aware prompt for the deliverable."""
        
        # Extract brand elements
        colors = brand_guidelines.get("colors", [])
        style = brand_guidelines.get("style", "modern and professional")
        mood = brand_guidelines.get("mood", "professional")
        fonts = brand_guidelines.get("fonts", [])
        
        # Build color string
        color_str = f"Colors: {', '.join(colors)}" if colors else ""
        font_str = f"Fonts: {', '.join(fonts)}" if fonts else ""
        
        # Get reference to first asset (usually logo) for consistency
        logo_reference = ""
        if previous_assets and previous_assets[0].get("type") in ["logo", "brand_identity"]:
            logo_reference = f"Maintain visual consistency with the brand logo and identity."
        
        # Deliverable-specific templates
        templates = {
            "logo": f"""Professional logo design. {campaign_brief}
Style: {style}
{color_str}
Requirements: Clean, scalable, memorable, works in color and black/white
Mood: {mood}""",
            
            "business_card": f"""Professional business card design. {campaign_brief}
Style: {style}
{color_str}
{font_str}
{logo_reference}
Layout: Standard business card (3.5" x 2"), clean and professional""",
            
            "social_media_kit": f"""Social media post template. {campaign_brief}
Style: {style}
{color_str}
{logo_reference}
Format: Instagram post (1080x1080), eye-catching, mobile-optimized""",
            
            "instagram_post": f"""Instagram post design. {campaign_brief}
Style: {style}
{color_str}
{logo_reference}
Format: Square 1080x1080, scroll-stopping, clear message""",
            
            "product_mockup": f"""Professional product photography. {campaign_brief}
Style: {style}, photorealistic
{color_str}
Lighting: Professional studio lighting, clean background
Mood: {mood}, premium quality""",
            
            "hero_image": f"""Website hero section image. {campaign_brief}
Style: {style}
{color_str}
{logo_reference}
Format: Wide banner, professional, attention-grabbing""",
            
            "video_ad": f"""Marketing video concept. {campaign_brief}
Style: {style}
{color_str}
Mood: {mood}, engaging and dynamic
Duration: 5 seconds, professional quality"""
        }
        
        # Get template or use generic
        if deliverable_type in templates:
            prompt = templates[deliverable_type]
        else:
            prompt = f"""{deliverable_type} for campaign. {campaign_brief}
Style: {style}
{color_str}
{logo_reference}
Mood: {mood}"""
        
        return prompt
    
    def _get_asset_dimensions(self, deliverable_type: str) -> tuple:
        """Get appropriate dimensions for asset type."""
        
        dimensions = {
            "logo": (1024, 1024),
            "business_card": (1050, 600),  # 3.5" x 2" at 300dpi
            "letterhead": (816, 1056),     # 8.5" x 11" at 96dpi
            "social_media_kit": (1080, 1080),
            "instagram_post": (1080, 1080),
            "instagram_story": (1080, 1920),
            "facebook_post": (1200, 630),
            "twitter_header": (1500, 500),
            "linkedin_post": (1200, 627),
            "hero_image": (1920, 1080),
            "hero_section": (1920, 1080),
            "banner": (1920, 600),
            "cta_banner": (1200, 400),
            "product_mockup": (1024, 1024),
            "event_poster": (1080, 1350),
            "email_header": (600, 200),
            "favicon": (512, 512)
        }
        
        return dimensions.get(deliverable_type, (1024, 1024))
    
    def generate_campaign_summary(self, campaign_results: Dict[str, Any]) -> str:
        """Generate a human-readable campaign summary."""
        
        total = len(campaign_results["deliverables"])
        successful = campaign_results["success_count"]
        
        summary = f"""
🎨 Campaign Generation Complete!

Campaign Type: {campaign_results['campaign_type'].replace('_', ' ').title()}
Brief: {campaign_results['campaign_brief'][:100]}...

📊 Results:
- Total Deliverables: {total}
- Successfully Generated: {successful}
- Success Rate: {(successful/total*100):.0f}%

📦 Generated Assets:
"""
        
        for asset in campaign_results["assets"]:
            if asset.get("status") != "failed":
                asset_type = asset["type"].replace("_", " ").title()
                url = asset.get("url", "N/A")
                summary += f"  ✅ {asset_type}: {url}\n"
            else:
                asset_type = asset["type"].replace("_", " ").title()
                summary += f"  ❌ {asset_type}: Failed\n"
        
        summary += f"\n🎨 Brand Guidelines Applied:\n"
        guidelines = campaign_results["brand_guidelines"]
        if guidelines.get("colors"):
            summary += f"  - Colors: {', '.join(guidelines['colors'])}\n"
        if guidelines.get("style"):
            summary += f"  - Style: {guidelines['style']}\n"
        if guidelines.get("mood"):
            summary += f"  - Mood: {guidelines['mood']}\n"
        
        return summary

    def _get_reference_image(self, brand_guidelines: Dict[str, Any], deliverable_type: str) -> Optional[str]:
        """
        Extract reference image URL from brand guidelines.
        Prioritizes logo for brand consistency.
        
        Args:
            brand_guidelines: Brand guidelines containing assets
            deliverable_type: Type of deliverable being generated
            
        Returns:
            URL of reference image or None
        """
        # Check if brand_guidelines has logo URL directly
        if isinstance(brand_guidelines, dict):
            # Check for logo in visual_style
            visual_style = brand_guidelines.get("visual_style", {})
            if isinstance(visual_style, dict):
                logo_data = visual_style.get("logo", {})
                if isinstance(logo_data, dict) and logo_data.get("url"):
                    return logo_data["url"]
            
            # Check for logo in assets
            assets = brand_guidelines.get("assets", {})
            if isinstance(assets, dict) and assets.get("logo_url"):
                return assets["logo_url"]
            
            # Check for logo_url directly in guidelines
            if brand_guidelines.get("logo_url"):
                return brand_guidelines["logo_url"]
        
        return None
    
    def _size_to_aspect_ratio(self, size: tuple) -> str:
        """
        Convert size tuple to aspect ratio string for Nano Banana.
        
        Args:
            size: Tuple of (width, height)
            
        Returns:
            Aspect ratio string like "1:1", "16:9", "9:16"
        """
        width, height = size
        
        # Calculate ratio
        if width == height:
            return "1:1"
        elif width > height:
            # Landscape
            ratio = width / height
            if 1.7 <= ratio <= 1.8:
                return "16:9"
            elif 1.3 <= ratio <= 1.4:
                return "4:3"
            else:
                return "16:9"  # Default landscape
        else:
            # Portrait
            ratio = height / width
            if 1.7 <= ratio <= 1.8:
                return "9:16"
            elif 1.3 <= ratio <= 1.4:
                return "3:4"
            else:
                return "9:16"  # Default portrait
