"""
One-off script to test that HuggingFace Inference API returns embeddings
from BGE-M3 model.

Usage:
    cd backend
    export HUGGINGFACE_API_KEY="hf_xxx"
    uv run python scripts/test_embeddings.py
"""
import asyncio
import os
import sys

# Add backend root to path so 'app' package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.llm.huggingface_provider import HuggingFaceProvider


async def main():
    api_key = os.environ.get("HUGGINGFACE_API_KEY")
    if not api_key:
        print("ERROR: HUGGINGFACE_API_KEY not set")
        sys.exit(1)

    print(f"API key present (first 10 chars): {api_key[:10]}...")
    print("Model: BAAI/bge-m3")
    print()

    provider = HuggingFaceProvider(api_key=api_key, embedding_model="BAAI/bge-m3")

    # Test 1: Spanish text
    print("--- Test 1: Spanish text ---")
    text_es = "Senior Python developer con experiencia en FastAPI y PostgreSQL"
    embedding = await provider.generate_embedding(text_es)
    print(f"  Input length: {len(text_es)} chars")
    print(f"  Vector dimension: {len(embedding.vector)}")
    print("  Expected dimension: 1024")
    print(f"  Match: {'OK' if len(embedding.vector) == 1024 else 'FAIL'}")
    print(f"  Model: {embedding.model}")
    print(f"  Provider: {embedding.provider}")

    # Verify determinism: same text should produce same embedding
    print()
    print("--- Test 2: Determinism (same input → same output) ---")
    embedding2 = await provider.generate_embedding(text_es)
    same = embedding.vector == embedding2.vector
    print(f"  Same vector: {'OK' if same else 'FAIL'}")

    # Verify normalization (L2 norm should be ~1.0)
    print()
    print("--- Test 3: Vector normalization ---")
    import math
    norm = math.sqrt(sum(x * x for x in embedding.vector))
    print(f"  L2 norm: {norm:.6f}")
    print("  Expected: ~1.0")
    print(f"  Acceptable: {'OK' if 0.99 < norm < 1.01 else 'FAIL'}")

    # Test 4: Cross-lingual (English)
    print()
    print("--- Test 4: English text (cross-lingual test) ---")
    text_en = "Senior Python developer with FastAPI and PostgreSQL experience"
    embedding_en = await provider.generate_embedding(text_en)
    print(f"  Input length: {len(text_en)} chars")
    print(f"  Vector dimension: {len(embedding_en.vector)}")

    # Cross-lingual similarity: similar text in different languages should have
    # high cosine similarity (this is the BGE-M3 strength).
    print()
    print("--- Test 5: Cross-lingual similarity (ES vs EN, same meaning) ---")
    def cosine_similarity(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        return dot  # vectors are normalized so dot product = cosine sim

    sim = cosine_similarity(embedding.vector, embedding_en.vector)
    print(f"  Cosine similarity: {sim:.4f}")
    print("  Expected: high (>0.8) because BGE-M3 is multilingual")
    print(f"  Verdict: {'OK (multilingual works)' if sim > 0.7 else 'CHECK (lower than expected)'}")


if __name__ == "__main__":
    asyncio.run(main())
