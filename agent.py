"""
LangChain Agent Implementation for Flight Booking Tickets
COMPLETE LOGIC FLOW EXPLAINED
"""

from langchain_anthropic import ChatAnthropic
from langchain.tools import tool
from langchain.agents import create_agent
import json
from typing import Optional, Dict, Any

# ============================================
# STEP 1: DEFINE TOOLS (What agent CAN do)
# ============================================

@tool
def extract_booking_info(email_content: str) -> str:
    """
    Extract travel booking details from customer email.
    
    Args:
        email_content: The customer's email text
        
    Returns:
        JSON with extracted booking details
    """
    # Agent will call this first to structure the data
    # This is a placeholder - agent will actually parse the email
    return json.dumps({
        "intent": "flight_booking",
        "origin": None,
        "destination": None,
        "departure_date": None,
        "return_date": None,
        "trip_type": None,
        "passengers": None
    })


@tool
def validate_booking_requirements(booking_info: str) -> str:
    """
    Check if all required booking information is present.
    Returns what's missing if incomplete.
    
    Args:
        booking_info: JSON string with booking details
        
    Returns:
        Validation result with status and missing fields
    """
    try:
        data = json.loads(booking_info)
        
        # Required fields for ANY booking
        base_required = ["origin", "destination", "departure_date", "passengers"]
        missing = []
        
        for field in base_required:
            if not data.get(field) or data.get(field) == "None":
                missing.append(field)
        
        # Special logic for round trips
        if data.get("trip_type") == "round_trip":
            if not data.get("return_date") or data.get("return_date") == "None":
                missing.append("return_date")
        
        # LOGIC DECISION POINT
        if missing:
            return json.dumps({
                "status": "incomplete",
                "missing_fields": missing,
                "action": "request_missing_info"
            })
        else:
            return json.dumps({
                "status": "complete",
                "missing_fields": [],
                "action": "search_flights"
            })
            
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def search_flights(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: Optional[str] = None,
    passengers: int = 1
) -> str:
    """
    Search for available flights using Flight API.
    ONLY called when ALL required info is present.
    
    Args:
        origin: Departure airport/city
        destination: Arrival airport/city
        departure_date: Format YYYY-MM-DD
        return_date: Format YYYY-MM-DD (for round trips)
        passengers: Number of passengers
        
    Returns:
        JSON with available flight options
    """
    
    # ===================================
    # TODO: REPLACE WITH YOUR FLIGHT API
    # ===================================
    
    # Example API call structure:
    """
    import requests
    
    api_url = "https://your-flight-api.com/search"
    params = {
        "from": origin,
        "to": destination,
        "departure": departure_date,
        "return": return_date,
        "passengers": passengers
    }
    
    response = requests.get(api_url, params=params)
    flights_data = response.json()
    """
    
    # MOCK RESPONSE FOR NOW
    flights = {
        "search_successful": True,
        "trip_type": "round_trip" if return_date else "one_way",
        "outbound_flights": [
            {
                "flight_number": "AA123",
                "airline": "American Airlines",
                "departure_time": f"{departure_date} 08:00 AM",
                "arrival_time": f"{departure_date} 12:30 PM",
                "price_usd": 450.00,
                "available_seats": 12
            },
            {
                "flight_number": "UA456",
                "airline": "United Airlines",
                "departure_time": f"{departure_date} 10:30 AM",
                "arrival_time": f"{departure_date} 15:00 PM",
                "price_usd": 425.00,
                "available_seats": 8
            }
        ]
    }
    
    if return_date:
        flights["return_flights"] = [
            {
                "flight_number": "AA789",
                "airline": "American Airlines",
                "departure_time": f"{return_date} 02:00 PM",
                "arrival_time": f"{return_date} 06:30 PM",
                "price_usd": 420.00,
                "available_seats": 15
            }
        ]
    
    return json.dumps(flights, indent=2)


# ============================================
# STEP 2: CREATE AGENT WITH LOGIC FLOW
# ============================================

def create_booking_agent():
    """Create agent that handles the complete workflow"""
    
    llm = ChatAnthropic(
        model="claude-sonnet-4-20250514",
        temperature=0,
        max_tokens=4000
    )
    
    tools = [
        extract_booking_info,
        validate_booking_requirements,
        search_flights
    ]
    
    # THIS IS WHERE THE LOGIC IS DEFINED
    system_prompt = """You are a travel booking assistant. Follow this EXACT workflow:

WORKFLOW STEPS:
1️⃣ First, analyze the customer's email to extract booking details
2️⃣ Use validate_booking_requirements to check if info is complete
3️⃣ Based on validation result:
   
   IF STATUS = "incomplete":
   - Create a polite email asking for missing information
   - List what's missing specifically
   - DO NOT search for flights
   - STOP here and return the email
   
   IF STATUS = "complete":
   - Call search_flights with the extracted information
   - Format flight options into a nice email
   - Include prices, times, and flight numbers
   - STOP here and return the email

TRIP TYPE RULES:
- ONE date + no mention of "round trip" = ONE-WAY trip
- ONE date + mentions "round trip/return" = INCOMPLETE (need return date)
- TWO dates provided = ROUND TRIP

EMAIL FORMAT:
- Start with: "Dear Customer,"
- End with: "Best regards,\\nTravel Booking Team"
- Be professional and helpful
- Use HTML line breaks: <br> for formatting

NEVER:
- Assume or invent dates
- Search flights if information is missing
- Ask for info that was already provided

Always use the tools to make decisions, don't guess."""
    
    agent = create_agent(
        llm,
        tools,
        state_modifier=system_prompt,
    )
    
    return agent


# ============================================
# STEP 3: MAIN PROCESSING FUNCTION
# ============================================

def analyze_ticket_with_agent(thread_json: Dict[str, Any]) -> Dict[str, str]:
    """
    THIS IS WHAT REPLACES YOUR analyze_thread_single_call() from slm.py
    
    LOGIC FLOW:
    1. Agent reads the email thread
    2. Agent validates if info is complete
    3. IF INCOMPLETE → Returns email asking for missing info
    4. IF COMPLETE → Calls flight API → Returns email with flight options
    
    Args:
        thread_json: Same format as your current system
            {
                "ticket_id": "12345",
                "customer_email": "customer@example.com",
                "subject": "Flight request",
                "messages": [
                    {"email_date": "...", "email_content": "..."}
                ]
            }
    
    Returns:
        {
            "type": "info_missing" | "present" | "non_valid" | "error",
            "msg": "Email content ready to send to customer",
            "values": {...}  # Optional: extracted booking info
        }
    """
    try:
        agent = create_booking_agent()
        
        # Format the conversation history
        conversation = "\n\n".join([
            f"Date: {msg['email_date']}\nContent: {msg['email_content']}"
            for msg in thread_json.get("messages", [])
        ])
        
        # Prepare the input for the agent
        input_msg = f"""
Analyze this customer ticket:

TICKET: #{thread_json['ticket_id']}
CUSTOMER: {thread_json['customer_email']}
SUBJECT: {thread_json['subject']}

EMAIL CONVERSATION:
{conversation}

Follow the workflow to either:
1. Ask for missing information (if incomplete)
2. Search flights and present options (if complete)
"""
        
        # Run the agent (this is where magic happens)
        config = {"configurable": {"thread_id": thread_json['ticket_id']}}
        result = agent.invoke(
            {"messages": [("user", input_msg)]},
            config=config
        )
        
        # Extract the final message from agent
        final_message = result["messages"][-1].content
        
        # ============================================
        # DETERMINE RESPONSE TYPE by checking what tools were used
        # ============================================
        
        agent_actions = str(result.get("messages", []))
        
        response_type = "info_missing"  # Default
        extracted_values = {}
        
        # Check if agent searched for flights
        if "search_flights" in agent_actions:
            response_type = "present"  # Complete booking
            # Extract flight search parameters for your records
            try:
                for msg in result["messages"]:
                    if hasattr(msg, 'tool_calls') and msg.tool_calls:
                        for tool_call in msg.tool_calls:
                            if tool_call['name'] == 'search_flights':
                                extracted_values = tool_call['args']
            except:
                pass
        
        # Check if validation found missing info
        elif "incomplete" in agent_actions or "missing" in final_message.lower():
            response_type = "info_missing"
        
        # Check if not booking-related
        elif "not a booking" in final_message.lower() or "cannot help" in final_message.lower():
            response_type = "non_valid"
        
        return {
            "type": response_type,
            "msg": final_message,  # Ready to send as email
            "values": extracted_values  # Optional: for your records
        }
        
    except Exception as e:
        # Fallback error response
        return {
            "type": "error",
            "msg": (
                "Dear Customer,<br><br>"
                "We encountered an issue processing your request. "
                "Our support team will manually review your inquiry.<br><br>"
                "Best regards,<br>Travel Booking Team"
            ),
            "error_details": str(e)
        }


# ============================================
# STEP 4: INTEGRATION WITH YOUR zoho_api.py
# ============================================

"""
In your zoho_api.py file, replace this line:

    # OLD CODE:
    from slm import analyze_thread_single_call
    llm_result = analyze_thread_single_call(thread_json)
    
    # NEW CODE:
    from langchain_agent import analyze_ticket_with_agent
    llm_result = analyze_ticket_with_agent(thread_json)

That's it! Everything else stays the same because the return format is identical.
"""


# ============================================
# EXAMPLE USAGE & TEST CASES
# ============================================

if __name__ == "__main__":
    
    print("="*60)
    print("TEST CASE 1: INCOMPLETE INFO (Missing return date)")
    print("="*60)
    
    incomplete_ticket = {
        "ticket_id": "12345",
        "customer_email": "john@example.com",
        "subject": "Flight booking",
        "messages": [
            {
                "email_date": "2024-12-01 10:00",
                "email_content": "Hi, I need a round trip flight from NYC to London departing Dec 15th. 2 passengers."
            }
        ]
    }
    
    result1 = analyze_ticket_with_agent(incomplete_ticket)
    print(f"\nType: {result1['type']}")
    print(f"Message:\n{result1['msg']}\n")
    
    # Expected: type = "info_missing"
    # Expected: msg asks for return date
    
    
    print("="*60)
    print("TEST CASE 2: COMPLETE INFO")
    print("="*60)
    
    complete_ticket = {
        "ticket_id": "67890",
        "customer_email": "sarah@example.com",
        "subject": "Need flight",
        "messages": [
            {
                "email_date": "2024-12-01 11:00",
                "email_content": "Hello, I need a round trip from Dubai to Paris. Departing Jan 10th, returning Jan 20th. 1 passenger."
            }
        ]
    }
    
    result2 = analyze_ticket_with_agent(complete_ticket)
    print(f"\nType: {result2['type']}")
    print(f"Message:\n{result2['msg']}\n")
    
    # Expected: type = "present"
    # Expected: msg contains flight options with prices and times
    
    
    print("="*60)
    print("TEST CASE 3: ONE-WAY TRIP")
    print("="*60)
    
    oneway_ticket = {
        "ticket_id": "11111",
        "customer_email": "mike@example.com",
        "subject": "One way flight",
        "messages": [
            {
                "email_date": "2024-12-01 12:00",
                "email_content": "I need a one-way flight from Boston to Seattle on December 25th. 1 passenger."
            }
        ]
    }
    
    result3 = analyze_ticket_with_agent(oneway_ticket)
    print(f"\nType: {result3['type']}")
    print(f"Message:\n{result3['msg']}\n")
    
    # Expected: type = "present"
    # Expected: msg contains one-way flight options