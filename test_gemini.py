import asyncio
from pydantic_ai import Agent, BinaryContent
from pydantic_ai.models.gemini import GeminiModel
from pydantic_ai.providers.google_gla import GoogleGLAProvider
from dotenv import load_dotenv
import os

load_dotenv()

def read_api_key_from_file(file_path='appSetting.txt'):
    try:
        with open(file_path, 'r') as f:
            for line in f:
                if line.startswith('GEMINI_API_KEY='):
                    return line.split('=', 1)[1].strip()
    except Exception as e:
        raise RuntimeError(f"Failed to read API key from {file_path}: {e}")
    raise ValueError("GEMINI_API_KEY not found in appSetting.txt")

GEMINI_API_KEY = read_api_key_from_file()

provider = GoogleGLAProvider(api_key=GEMINI_API_KEY)
model = GeminiModel('gemini-2.0-flash-lite', provider=provider)
gemini_agent = Agent(model)

async def test():
    prompt = "Return a simple JSON object: {\"test\": \"hello\"}"
    
    result = await gemini_agent.run(prompt)
    
    print(f"Result type: {type(result)}")
    print(f"Result attributes: {[attr for attr in dir(result) if not attr.startswith('_')]}")
    print(f"\nHas 'data': {hasattr(result, 'data')}")
    print(f"Has 'output': {hasattr(result, 'output')}")
    
    if hasattr(result, 'data'):
        print(f"\nresult.data type: {type(result.data)}")
        print(f"result.data value: {result.data}")
    
    if hasattr(result, 'output'):
        print(f"\nresult.output type: {type(result.output)}")
        print(f"result.output value: {result.output}")
    
    print(f"\nstr(result): {str(result)}")
    print(f"\nrepr(result): {repr(result)}")

if __name__ == "__main__":
    asyncio.run(test())
