response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user",
        "content": "What is AI?"}],
    temperature=1
)
