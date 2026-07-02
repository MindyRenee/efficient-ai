"""Demo client that pays Efficient AI's x402 proxy per request."""
import os
import sys

import httpx


def main():
    proxy_url = os.environ.get("EFFICIENT_PROXY_URL", "http://localhost:8000")
    private_key = os.environ.get("PRIVATE_KEY")
    if not private_key:
        print("Set PRIVATE_KEY env var to a Base wallet with USDC")
        sys.exit(1)

    try:
        from x402 import x402ClientSync
        from x402.mechanisms.evm.exact import ExactEvmScheme
        from x402.signers.evm import EvmSigner
    except ImportError as e:
        print(f"Install x402[evm]: {e}")
        sys.exit(1)

    signer = EvmSigner(private_key)
    client = x402ClientSync()
    client.register("eip155:8453", ExactEvmScheme(signer=signer))

    url = f"{proxy_url}/v1/chat/completions"
    body = {"model": "auto", "messages": [{"role": "user", "content": "What is 2 + 2?"}]}

    # First call without payment to get requirements
    resp = httpx.post(url, json=body)
    if resp.status_code == 402:
        requirements = resp.json()
        print(f"Payment required: {requirements}")
        payload = client.create_payment_payload(requirements)
        resp = httpx.post(url, json=body, headers={"PAYMENT-SIGNATURE": payload})

    print(resp.status_code, resp.text)


if __name__ == "__main__":
    main()
