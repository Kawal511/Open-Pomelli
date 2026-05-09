#!/usr/bin/env python3
# variation_generator.py
"""
Asset Variation Generator - Creates multiple variations of designs
Generates 3-5 variations with different styles, colors, or compositions.
"""

from typing import Dict, Any, List
from datetime import datetime


class VariationGenerator:
    """
    Generates multiple variations of design concepts for user selection.
    """
    
    VARIATION_STRATEGIES = {
        "style": [
            "minimalist and clean",
            "bold and modern",
            "elegant and refined",
            "playful and energetic",
            "professional and corporate"
        ],
        "color": [
            "warm earth tones (browns, oranges, yellows)",
            "cool blues and grays",
            "vibrant and colorful (rainbow palette)",
            "monochromatic black and white",
            "pastel soft colors"
        ],
        "mood": [
            "professional and serious",
            "friendly and approachable",
            "luxurious and premium",
            "fun and playful",
            "calm and peaceful"
        ],
        "composition": [
            "centered and symmetrical",
            "dynamic diagonal layout",
            "asymmetric modern layout",
            "grid-based structured",
            "organic flowing design"
        ]
    }
    
    def __init__(self, agent):
        """
        Initialize variation generator.
        
        Args:
            agent: Reference to the main MarketingAgent instance
        """
        self.agent = agent
        print("[VariationGenerator] Initialized")
    
    async def generate_variations(
        self,
        base_prompt: str,
        asset_type: str = "image",
        num_variations: int = 3,
        strategy: str = "style",
        brand_guidelines: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """
        Generate multiple variations of a design concept.
        
        Args:
            base_prompt: Base prompt describing what to create
            asset_type: Type of asset (image, logo, video, etc.)
            num_variations: Number of variations to generate (1-5)
            strategy: Variation strategy (style, color, mood, composition)
            brand_guidelines: Optional brand guidelines to maintain consistency
            
        Returns:
            List of variation results
        """
        print(f"\n[VariationGenerator] 🎨 Generating {num_variations} variations")
        print(f"[VariationGenerator] Strategy: {strategy}")
        print(f"[VariationGenerator] Base prompt: {base_prompt[:80]}...")
        
        # Limit variations to reasonable number
        num_variations = min(max(num_variations, 1), 5)
        
        # Get variation modifiers
        modifiers = self._get_variation_modifiers(strategy, num_variations)
        
        variations = []
        
        for idx, modifier in enumerate(modifiers, 1):
            print(f"\n[VariationGenerator] Creating variation {idx}/{num_variations}: {modifier}")
            
            try:
                # Build variation prompt
                variation_prompt = self._build_variation_prompt(
                    base_prompt=base_prompt,
                    modifier=modifier,
                    strategy=strategy,
                    brand_guidelines=brand_guidelines
                )
                
                # Generate the variation
                if asset_type == "video":
                    result = await self._generate_video_variation(variation_prompt)
                else:
                    result = await self._generate_image_variation(variation_prompt, asset_type)
                
                variation = {
                    "variation_number": idx,
                    "strategy": strategy,
                    "modifier": modifier,
                    "prompt": variation_prompt,
                    "result": result,
                    "asset_type": asset_type,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                variations.append(variation)
                print(f"[VariationGenerator] ✅ Variation {idx} complete")
                
            except Exception as e:
                print(f"[VariationGenerator] ⚠️ Variation {idx} failed: {e}")
                variations.append({
                    "variation_number": idx,
                    "strategy": strategy,
                    "modifier": modifier,
                    "status": "failed",
                    "error": str(e)
                })
        
        print(f"\n[VariationGenerator] 🎉 Generated {len([v for v in variations if 'result' in v])}/{num_variations} variations")
        
        return variations
    
    async def generate_ab_test_variations(
        self,
        base_prompt: str,
        test_elements: List[str],
        brand_guidelines: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Generate A/B test variations for specific elements.
        
        Args:
            base_prompt: Base design prompt
            test_elements: Elements to test (e.g., ["headline", "cta_color", "layout"])
            brand_guidelines: Brand guidelines
            
        Returns:
            A/B test results with variations
        """
        print(f"\n[VariationGenerator] 🧪 Generating A/B test variations")
        print(f"[VariationGenerator] Testing: {', '.join(test_elements)}")
        
        ab_results = {
            "base_prompt": base_prompt,
            "test_elements": test_elements,
            "variations": {}
        }
        
        for element in test_elements:
            print(f"\n[VariationGenerator] Testing element: {element}")
            
            # Generate 2 variations for this element
            variations = await self.generate_variations(
                base_prompt=base_prompt,
                num_variations=2,
                strategy=self._get_strategy_for_element(element),
                brand_guidelines=brand_guidelines
            )
            
            ab_results["variations"][element] = variations
        
        return ab_results
    
    def _get_variation_modifiers(self, strategy: str, num_variations: int) -> List[str]:
        """Get modifiers for the specified strategy."""
        
        if strategy in self.VARIATION_STRATEGIES:
            modifiers = self.VARIATION_STRATEGIES[strategy][:num_variations]
        else:
            # Fallback to style variations
            modifiers = self.VARIATION_STRATEGIES["style"][:num_variations]
        
        return modifiers
    
    def _build_variation_prompt(
        self,
        base_prompt: str,
        modifier: str,
        strategy: str,
        brand_guidelines: Dict[str, Any] = None
    ) -> str:
        """Build a prompt for a specific variation."""
        
        # Start with base prompt
        variation_prompt = base_prompt
        
        # Add strategy-specific modifier
        if strategy == "style":
            variation_prompt += f"\nStyle: {modifier}"
        elif strategy == "color":
            variation_prompt += f"\nColor palette: {modifier}"
        elif strategy == "mood":
            variation_prompt += f"\nMood and tone: {modifier}"
        elif strategy == "composition":
            variation_prompt += f"\nComposition: {modifier}"
        
        # Add brand guidelines if provided
        if brand_guidelines:
            if brand_guidelines.get("colors") and strategy != "color":
                variation_prompt += f"\nBrand colors: {', '.join(brand_guidelines['colors'])}"
            
            if brand_guidelines.get("fonts"):
                variation_prompt += f"\nTypography: {', '.join(brand_guidelines['fonts'])}"
        
        # Add quality requirements
        variation_prompt += "\nRequirements: Professional quality, high resolution, polished and refined"
        
        return variation_prompt
    
    async def _generate_image_variation(self, prompt: str, asset_type: str) -> Dict[str, Any]:
        """Generate an image variation."""
        
        # Determine size based on asset type
        size = (1024, 1024)  # Default square
        
        if asset_type == "logo":
            size = (1024, 1024)
        elif asset_type == "banner":
            size = (1920, 600)
        elif asset_type == "social_post":
            size = (1080, 1080)
        
        # Generate image
        urls = await self.agent.image_adapter.generate_image(prompt, size=size)
        url = urls[0] if urls else None
        
        # Store in assets
        asset = {
            "type": asset_type,
            "url": url,
            "prompt": prompt,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        self.agent.generated_assets.append(asset)
        
        return {
            "url": url,
            "type": "image",
            "dimensions": f"{size[0]}x{size[1]}"
        }
    
    async def _generate_video_variation(self, prompt: str) -> Dict[str, Any]:
        """Generate a video variation."""
        
        url = await self.agent.video_adapter.render({
            "prompt": prompt,
            "duration": 5,
            "resolution": "720p",
            "aspect_ratio": "16:9"
        })
        
        # Store in assets
        asset = {
            "type": "video",
            "url": url,
            "prompt": prompt,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        self.agent.generated_assets.append(asset)
        
        return {
            "url": url,
            "type": "video",
            "duration": 5
        }
    
    def _get_strategy_for_element(self, element: str) -> str:
        """Determine best variation strategy for an element."""
        
        element_strategies = {
            "headline": "composition",
            "cta_color": "color",
            "layout": "composition",
            "style": "style",
            "mood": "mood",
            "background": "color"
        }
        
        return element_strategies.get(element, "style")
    
    def create_variation_comparison(self, variations: List[Dict[str, Any]]) -> str:
        """Create a comparison summary of variations."""
        
        summary = f"\n🎨 Variation Comparison\n"
        summary += f"{'='*60}\n\n"
        
        for var in variations:
            if "result" in var:
                num = var["variation_number"]
                modifier = var["modifier"]
                url = var["result"].get("url", "N/A")
                
                summary += f"Variation {num}: {modifier}\n"
                summary += f"  URL: {url}\n"
                summary += f"  Prompt: {var['prompt'][:80]}...\n\n"
        
        summary += f"\n💡 Tip: Review all variations and choose the one that best fits your vision!\n"
        
        return summary
