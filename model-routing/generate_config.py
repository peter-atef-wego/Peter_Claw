#!/usr/bin/env python3
"""
Config Generator — Reads models.json and generates all dependent configs.

When you change L1-L4 models in models.json, run this to regenerate:
- openclaw.json (agent list)
- model_router.py (keywords)
- ROUTING.md (documentation)

Single source of truth → consistent everywhere.

Usage:
    python3 generate_config.py
    # Generates/updates: agent config, router, docs

    python3 generate_config.py --dry-run
    # Shows what would change
"""

import json
import sys
import os

MODEL_CONFIG_FILE = "models.json"

def load_models():
    """Load tier definitions from models.json"""
    with open(MODEL_CONFIG_FILE, "r") as f:
        return json.load(f)

def generate_agent_config(models):
    """Generate agent list for openclaw.json"""
    agents = [
        {"id": "main", "model": "openai-codex/gpt-5.2-codex"}
    ]
    
    for tier in models["tiers"]:
        agents.append({
            "id": tier["agent_id"],
            "model": f"{tier['provider']}/{tier['model']}"
        })
    
    return agents

def generate_router_keywords(models):
    """Generate keyword mappings for model_router.py"""
    keywords = {}
    for tier in models["tiers"]:
        keywords[tier["id"]] = tier["keywords"]
    return keywords

def generate_openclaw_models_section(models):
    """Generate models section for openclaw.json"""
    models_list = []
    for tier in models["tiers"]:
        models_list.append({
            "id": tier["model"],
            "name": f"{tier['name']} ({tier['cost_tier']})"
        })
    
    return {
        "mode": "merge",
        "providers": {
            "openrouter": {
                "api": "openai-completions",
                "baseUrl": "https://openrouter.ai/api/v1",
                "models": models_list
            }
        }
    }

def generate_routing_guide(models):
    """Generate human-readable ROUTING.md from models.json"""
    guide = """# Model Routing — 4-Tier System (Auto-Generated)

**Generated from:** `model-routing/models.json`  
**To update:** Edit models.json, then run `python3 generate_config.py`

---

## Tier Definitions

"""
    for tier in models["tiers"]:
        guide += f"""
### {tier['name']}

- **Model:** `{tier['model']}`
- **Provider:** {tier['provider']}
- **Cost:** {tier['cost_tier']}
- **Speed:** {tier['speed']}
- **Agent ID:** `{tier['agent_id']}`
- **Use Cases:** {', '.join(tier['use_cases'])}
- **Keywords:** {', '.join(tier['keywords'])}

"""
    
    return guide

def main():
    """Main generator"""
    dry_run = "--dry-run" in sys.argv
    
    print(f"Loading {MODEL_CONFIG_FILE}...")
    models = load_models()
    
    # Generate all configs
    agents = generate_agent_config(models)
    keywords = generate_router_keywords(models)
    openclaw_models = generate_openclaw_models_section(models)
    routing_guide = generate_routing_guide(models)
    
    print("✅ Generated configs:")
    print(f"  - {len(agents)} agent profiles")
    print(f"  - {len(keywords)} tier keyword mappings")
    print(f"  - OpenClaw models section")
    print(f"  - ROUTING.md documentation")
    
    if dry_run:
        print("\n[DRY RUN] Changes NOT applied. Remove --dry-run to update files.")
        return
    
    # Write files
    print("\nApplying changes...")
    
    # 1. Update openclaw.json agents
    try:
        openclaw_path = "../../openclaw.json"
        with open(openclaw_path, "r") as f:
            openclaw = json.load(f)
        
        openclaw["agents"]["list"] = agents
        openclaw["models"] = openclaw_models
        
        with open(openclaw_path, "w") as f:
            json.dump(openclaw, f, indent=2)
        
        print(f"✅ Updated {openclaw_path}")
    except Exception as e:
        print(f"❌ Error updating openclaw.json: {e}")
    
    # 2. Update model_router.py keywords
    try:
        router_path = "model_router.py"
        with open(router_path, "r") as f:
            content = f.read()
        
        # Find and replace KEYWORDS dict
        keywords_json = json.dumps(keywords, indent=2)
        new_content = content.replace(
            'KEYWORDS = {',
            f'KEYWORDS = {keywords_json}'
        )
        
        with open(router_path, "w") as f:
            f.write(new_content)
        
        print(f"✅ Updated {router_path}")
    except Exception as e:
        print(f"❌ Error updating model_router.py: {e}")
    
    # 3. Generate ROUTING.md
    try:
        routing_path = "ROUTING.md"
        with open(routing_path, "w") as f:
            f.write(routing_guide)
        
        print(f"✅ Generated {routing_path}")
    except Exception as e:
        print(f"❌ Error generating ROUTING.md: {e}")
    
    print("\n✅ All configs updated from models.json")
    print("\nNext steps:")
    print("  1. git add model-routing/")
    print("  2. git commit -m 'model-routing: update all configs from models.json'")
    print("  3. git push")

if __name__ == "__main__":
    main()
