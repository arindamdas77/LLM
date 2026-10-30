from openai import OpenAI

client = OpenAI(api_key="sk-...")

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user",
        "content": "What is AI?"}]
)

print(response.choices[0].message.content)
