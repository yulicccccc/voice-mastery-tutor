"""Small local smoke test for AnkiConnect; no MCP client required."""

from anki_mcp_server import get_due_cards

if __name__ == "__main__":
    result = get_due_cards(deck="000-WuCai Inbox", limit=5)
    print(f"deck={result['deck']}")
    print(f"total_due={result['total_due']} returned={result['returned']}")
    for index, card in enumerate(result["cards"], start=1):
        print(f"{index}. card_id={card['card_id']} note_id={card['note_id']} model={card['model']}")
        print(f"   fields={list(card['fields'].keys())}")
