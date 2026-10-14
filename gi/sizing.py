"""Will it fit? The four calculations of Chapter 5.

Example:
    python -m gi.sizing --params 32 --bits 4.5 --layers 64 --kv-heads 8 \
        --head-dim 128 --context 32768 --users 1 --gpu-gb 24
"""
import argparse


def weights_gb(params_b, bits):
    """Weights (GB) = parameters (billions) x bits per parameter / 8."""
    return params_b * bits / 8


def kv_cache_gb(layers, kv_heads, head_dim, tokens, users=1, bytes_per_value=2):
    """KV cache = 2 x layers x KV heads x head dim x bytes, per token, per user."""
    per_token = 2 * layers * kv_heads * head_dim * bytes_per_value
    return per_token * tokens * users / 1e9


def overhead_gb(weights):
    return 1.2 + 0.05 * weights


def max_tokens_per_second(bandwidth_gb_s, weights):
    """Upper limit for one user: memory bandwidth / size of the weights."""
    return bandwidth_gb_s / weights


def plan(params_b, bits, layers, kv_heads, head_dim, context, users,
         kv_bytes=2, gpu_gb=None, bandwidth=None):
    w = weights_gb(params_b, bits)
    kv = kv_cache_gb(layers, kv_heads, head_dim, context, users, kv_bytes)
    oh = overhead_gb(w)
    total = w + kv + oh
    out = {"weights_gb": w, "kv_cache_gb": kv, "overhead_gb": oh, "total_gb": total}
    if gpu_gb:
        out["fits_with_10pct_spare"] = total <= gpu_gb * 0.9
    if bandwidth:
        out["max_tokens_per_s"] = max_tokens_per_second(bandwidth, w)
    return out


def main():
    ap = argparse.ArgumentParser(description="Will it fit? (Governed Intelligence, Chapter 5)")
    ap.add_argument("--params", type=float, required=True, help="parameters in billions, e.g. 32")
    ap.add_argument("--bits", type=float, default=16, help="16, 8.5 (8-bit) or 4.5 (4-bit)")
    ap.add_argument("--layers", type=int, required=True)
    ap.add_argument("--kv-heads", type=int, required=True)
    ap.add_argument("--head-dim", type=int, required=True)
    ap.add_argument("--context", type=int, default=8192, help="tokens per user")
    ap.add_argument("--users", type=int, default=1, help="users at the same time")
    ap.add_argument("--kv-bytes", type=float, default=2, help="2 for a 16-bit cache, 1 for 8-bit")
    ap.add_argument("--gpu-gb", type=float, help="GPU memory to compare with")
    ap.add_argument("--bandwidth", type=float, help="memory bandwidth in GB/s")
    a = ap.parse_args()
    r = plan(a.params, a.bits, a.layers, a.kv_heads, a.head_dim, a.context, a.users,
             a.kv_bytes, a.gpu_gb, a.bandwidth)
    print(f"Weights   ≈ {r['weights_gb']:.1f} GB")
    print(f"KV cache  ≈ {r['kv_cache_gb']:.1f} GB")
    print(f"Overhead  ≈ {r['overhead_gb']:.1f} GB")
    print(f"Total     ≈ {r['total_gb']:.1f} GB")
    if "fits_with_10pct_spare" in r:
        print("Fits (with 10% spare):", "yes" if r["fits_with_10pct_spare"] else "no")
    if "max_tokens_per_s" in r:
        print(f"Speed limit for one user ≈ {r['max_tokens_per_s']:.0f} tokens/s (real speed is lower)")
    print("These are estimates. Test with your own prompts before you buy.")


if __name__ == "__main__":
    main()
