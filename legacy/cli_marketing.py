#!/usr/bin/env python3
# cli_marketing.py
"""
Simple CLI for the Marketing Agent (Pomelli-style)
"""

import asyncio
from marketing_agent_core import MarketingAgent


async def main():
    """Main CLI loop for marketing agent."""
    
    print("=" * 80)
    print("🎯 MARKETING AGENT - Your AI Marketing Department")
    print("   Similar to Google's Pomelli")
    print("=" * 80)
    print()
    print("I help you create on-brand marketing campaigns!")
    print()
    print("Features:")
    print("  • Brand DNA Analysis - I'll analyze your website to understand your brand")
    print("  • Campaign Ideas - Tailored marketing campaigns for your goals")
    print("  • On-Brand Assets - Social posts, banners, ads that match your brand")
    print("  • Multi-Channel - Instagram, LinkedIn, Facebook, Twitter, Web, Email")
    print()
    print("Type 'exit' or 'quit' to end the session.")
    print("=" * 80)
    print()
    
    # Initialize agent
    agent = MarketingAgent()
    
    # Main conversation loop
    while True:
        try:
            # Get user input
            user_input = input("\n👤 You: ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() in ['exit', 'quit', 'bye']:
                print("\n👋 Thanks for using Marketing Agent! Good luck with your campaigns!")
                break
            
            # Process message
            print("\n⏳ Agent is thinking...")
            response = await agent.process_message(user_input)
            
            # Display response
            print("\n" + "=" * 80)
            
            # Show thinking process
            if response.get("thinking_process"):
                print(f"\n💭 Agent Thinking:")
                print(f"   {response['thinking_process'][:200]}...")
            
            # Show main message
            print(f"\n🎯 Agent:")
            print(f"   {response['agent_response']}")
            
            # Show brand DNA if extracted
            if response.get("brand_dna"):
                dna = response["brand_dna"]
                print(f"\n📊 Brand DNA Extracted:")
                print(f"   Brand: {dna.get('brand_name', 'N/A')}")
                print(f"   Industry: {dna.get('industry', 'N/A')}")
                print(f"   Tone: {', '.join(dna.get('tone_of_voice', []))}")
                print(f"   Colors: {', '.join(dna.get('visual_style', {}).get('colors', []))}")
                print(f"   Target Audience: {dna.get('target_audience', 'N/A')}")
            
            # Show generated assets
            if response.get("generated_assets"):
                print(f"\n🎨 Generated Assets:")
                for i, asset in enumerate(response["generated_assets"], 1):
                    asset_type = asset.get("type", "unknown")
                    url = asset.get("url") or asset.get("data", {}).get("image_url")
                    print(f"   {i}. {asset_type}: {url}")
            
            # Show copy variants
            if response.get("copy_variants"):
                print(f"\n✍️ Copy Variants:")
                for i, variant in enumerate(response["copy_variants"], 1):
                    print(f"   {i}. {variant}")
            
            # Show suggestions
            if response.get("suggestions"):
                print(f"\n💡 Suggestions:")
                for suggestion in response["suggestions"]:
                    print(f"   • {suggestion}")
            
            print("\n" + "=" * 80)
            
        except KeyboardInterrupt:
            print("\n\n👋 Session interrupted. Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")
            print("Let's try again...")


if __name__ == "__main__":
    asyncio.run(main())
