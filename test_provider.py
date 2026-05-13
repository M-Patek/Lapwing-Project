"""
Quick test script for the LLM provider system
Tests the abstract interface with different providers
"""
import asyncio
import os
from dotenv import load_dotenv

from llm_provider import (
    LLMProviderFactory,
    MultiProviderManager,
    LLMConfig,
    ProviderType,
)
from settings import Settings


async def test_provider(provider_type: ProviderType, name: str):
    """Test a specific provider"""
    print(f"\n{'='*50}")
    print(f"Testing {name} Provider")
    print(f"{'='*50}")

    try:
        settings = Settings()

        if provider_type == ProviderType.ANTHROPIC:
            if not settings.ANTHROPIC_API_KEY or settings.ANTHROPIC_API_KEY == "your-anthropic-key-here":
                print(f"[X] {name}: No API key configured")
                return False
            provider = LLMProviderFactory.create(
                ProviderType.ANTHROPIC,
                api_key=settings.ANTHROPIC_API_KEY,
                base_url=settings.ANTHROPIC_BASE_URL,
                model=settings.CHAT_MODEL or "claude-opus-4-7",
            )
        elif provider_type == ProviderType.DEEPSEEK:
            if not settings.DEEPSEEK_API_KEY:
                print(f"[X] {name}: No API key configured")
                return False
            provider = LLMProviderFactory.create(
                ProviderType.DEEPSEEK,
                api_key=settings.DEEPSEEK_API_KEY,
                base_url=settings.DEEPSEEK_BASE_URL,
            )
        elif provider_type == ProviderType.OPENAI:
            if not settings.OPENAI_API_KEY:
                print(f"[X] {name}: No API key configured")
                return False
            provider = LLMProviderFactory.create(
                ProviderType.OPENAI,
                api_key=settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_BASE_URL,
            )
        else:
            print(f"[X] Unknown provider type: {provider_type}")
            return False

        # Test chat
        print(f"\n[TEST] Testing chat...")
        config = LLMConfig(temperature=0.7, max_tokens=100)

        response = await provider.chat(
            prompt="你好！请简单介绍一下自己，只用一句话。",
            config=config,
        )

        print(f"[OK] Response received:")
        print(f"   Text: {response.text[:100]}...")
        print(f"   Model: {response.model}")
        print(f"   Provider: {response.provider.name}")

        if response.usage:
            print(f"   Tokens: {response.usage}")

        # Test embeddings (fallback)
        print(f"\n[STAT] Testing embeddings (fallback)...")
        embeddings = await provider.get_embeddings(["Hello world", "测试文本"])
        print(f"[OK] Got {len(embeddings.embeddings)} embeddings")
        print(f"   Dimension: {len(embeddings.embeddings[0])}")

        print(f"\n[OK] {name} provider test PASSED")
        return True

    except Exception as e:
        print(f"\n[X] {name} provider test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_multi_provider():
    """Test MultiProviderManager auto-detection"""
    print(f"\n{'='*50}")
    print(f"Testing MultiProviderManager")
    print(f"{'='*50}")

    try:
        settings = Settings()
        manager = MultiProviderManager(settings)

        print(f"\n[OK] Providers initialized:")
        print(f"   Chat: {manager.chat_provider.provider_type().name}")
        print(f"   Scene: {manager.scene_provider.provider_type().name}")

        # Test a simple conversation
        print(f"\n[TEST] Testing conversation...")
        config = LLMConfig(temperature=0.9, max_tokens=150)

        response = await manager.chat_provider.chat(
            prompt="你是Lapwing。请用温柔的方式打个招呼。",
            config=config,
        )

        print(f"[OK] Response:")
        print(f"   {response.text}")

        print(f"\n[OK] MultiProviderManager test PASSED")
        return True

    except Exception as e:
        print(f"\n[X] MultiProviderManager test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def chat_with_lapwing():
    """Simple chat with Lapwing using the new provider system"""
    print(f"\n{'='*50}")
    print(f"[CHAT] Chatting with Lapwing")
    print(f"{'='*50}")

    try:
        settings = Settings()
        manager = MultiProviderManager(settings)

        print(f"\nProvider: {manager.chat_provider.provider_type().name}")
        print(f"Model: {settings.CHAT_MODEL or 'auto-detected'}")
        print(f"\nType 'quit' to exit\n")

        history = []

        while True:
            user_input = input("You: ").strip()
            if user_input.lower() in ['quit', 'exit', 'q']:
                break

            if not user_input:
                continue

            # Build prompt with history
            prompt = f"你是Lapwing，一个温柔的女孩。请用第一人称回复。\n\n"
            for h in history[-6:]:  # Last 3 exchanges
                prompt += f"用户: {h['user']}\nLapwing: {h['assistant']}\n\n"
            prompt += f"用户: {user_input}\nLapwing:"

            config = LLMConfig(
                temperature=0.95,
                max_tokens=200,
                system_prompt="你是Lapwing，一个温柔、安静的女孩，深爱着你的主人。用第一人称回复，语气温柔自然。"
            )

            print("Lapwing: ", end="", flush=True)

            # Stream response
            full_response = ""
            async for chunk in manager.chat_provider.chat_stream(prompt, config):
                print(chunk, end="", flush=True)
                full_response += chunk

            print()  # New line

            # Save to history
            history.append({
                "user": user_input,
                "assistant": full_response.strip(),
            })

        print("\n[BYE] Goodbye!")

    except KeyboardInterrupt:
        print("\n\n[BYE] Goodbye!")
    except Exception as e:
        print(f"\n[X] Error: {e}")
        import traceback
        traceback.print_exc()


async def main():
    """Main test runner"""
    load_dotenv()

    print("Lapwing LLM Provider Test Suite")
    print("=" * 50)

    # Run tests
    results = []

    # Test individual providers (only if configured)
    # results.append(await test_provider(ProviderType.ANTHROPIC, "Anthropic"))
    # results.append(await test_provider(ProviderType.DEEPSEEK, "DeepSeek"))
    # results.append(await test_provider(ProviderType.OPENAI, "OpenAI"))

    # Test multi-provider manager
    results.append(await test_multi_provider())

    # Summary
    print(f"\n{'='*50}")
    print(f"[STAT] Test Summary")
    print(f"{'='*50}")
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")

    if passed == total:
        print(f"\n[SUCCESS] All tests passed!")
        # Start chat
        await chat_with_lapwing()
    else:
        print(f"\n[WARN] Some tests failed. Check your configuration.")


if __name__ == "__main__":
    asyncio.run(main())
