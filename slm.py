import json
from ollama import chat
import configparser



def analyze_thread_single_call(thread_json):
    try:
        response = chat(
            model="phi4",
            messages=[{
                "role": "user",
                "content": (
                    "You are an assistant for a travel booking service.\n"
                    "Your task is to analyze the customer's email conversation and extract accurate travel booking details.\n\n"

                    "CONVERSATION FORMAT YOU WILL RECEIVE:\n"
                    "The key 'messages' contains a list of items, each with:\n"
                    "- 'email_date' → when the customer sent the message\n"
                    "- 'email_content' → the full written email including reply history\n\n"

                    "HOW TO UNDERSTAND EMAIL_CONTENT:\n"
                    "- The customer-provided information is always near the top of the email body.\n"
                    "- Text that begins with patterns like 'On ... wrote:' or lines starting with '>' are quoted system messages or agent replies.\n"
                    "- Keep the quoted text in memory for context, but do NOT treat it as new or missing information.\n\n"

                    "TRIP TYPE & DATE INTERPRETATION RULES (DO NOT DEVIATE FROM THESE RULES):\n"
                    "1. If the customer provides TWO dates:\n"
                    "      → Trip type = round trip\n"
                    "      → starting_date = earlier date\n"
                    "      → ending_date = later date\n"
                    "\n"
                    "2. If the customer provides ONE date AND does NOT mention 'round', 'round trip', 'return':\n"
                    "      → Trip type = one-way\n"
                    "      → ending_date = starting_date (same date)\n"
                    "\n"
                    "3. If the customer provides ONE date AND DOES mention 'round', 'round trip', 'return':\n"
                    "      → Trip type = round trip BUT information is INCOMPLETE\n"
                    "      → You MUST request the missing return date (ending_date)\n"
                    "\n"
                    "4. If ZERO dates are found:\n"
                    "      → Not enough information → request travel dates\n"
                    "\n"
                    "NEVER assume or invent a return date.\n"
                    "NEVER auto-fill ending_date = starting_date when customer explicitly requests round trip.\n"
                    "\n"
                    "WHEN TO RESPOND WITH EACH TYPE:\n"
                    "- type = 'non_valid' → no flight or booking intent\n"
                    "- type = 'info_missing' → booking intent exists but required fields are missing\n"
                    "- type = 'present' → all required booking information is available\n\n"

                    "OUTPUT JSON RULE:\n"
                    "You must respond ONLY with a JSON object:\n"
                    "{\n"
                    '  "type": "...",\n'
                    '  "msg": "email reply to customer",\n'
                    '  "values": { ... },        # only for type = present or info_missing\n'
                    '  "missing_values": [ ... ] # only for type = info_missing\n'
                    "}\n"
                    "No markdown. No backticks. No explanations.\n"
                    "The 'msg' must be a professional email starting with 'Dear Customer,' and ending with 'Best regards,\\nTravel Booking Team'.\n\n"

                    "Email messages to analyze (in chronological order):\n"
                    f"{json.dumps(thread_json['messages'], indent=2)}"
                )
            }]
        )

        content = response.message.content.strip()

        # Clean markdown wrappers (LLMs sometimes add ```json)
        if content.startswith("```"):
            lines = content.split('\n')
            lines = lines[1:] if lines[0].startswith("```") else lines
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = '\n'.join(lines)
        content = content.strip()

        result = json.loads(content)

        if "type" not in result or "msg" not in result:
            raise ValueError("Response missing required fields 'type' or 'msg'")

        return result

    except json.JSONDecodeError as e:
        return {
            "type": "error",
            "msg": (
                "Dear Customer,\n\n"
                "We encountered an issue processing your request. "
                "Our support team will manually review your inquiry and assist you shortly.\n\n"
                "Best regards,\nTravel Booking Team"
            ),
            "error_details": f"JSON parse error: {str(e)}",
            "raw_response": response.message.content if 'response' in locals() else None
        }
    except Exception as e:
        return {
            "type": "error",
            "msg": (
                "Dear Customer,\n\n"
                "An unexpected error occurred while processing your request. "
                "Our team has been notified and will respond as soon as possible.\n\n"
                "Best regards,\nTravel Booking Team"
            ),
            "error_details": str(e)
        }
