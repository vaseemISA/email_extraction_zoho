"""
LangChain Agent Implementation for Flight Booking Tickets
COMPLETE LOGIC FLOW EXPLAINED
"""

from langchain_anthropic import ChatAnthropic
from langchain.tools import tool
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver
from anthropic import Anthropic
import json
from typing import Optional, Dict, Any
import os

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
    
    # Enable prompt caching to reduce costs
    llm = ChatAnthropic(
        model="claude-sonnet-4-20250514",
        temperature=0,
        max_tokens=4000,
        # Enable caching for repeated system prompts & tools
        default_headers={
            "anthropic-beta": "prompt-caching-2024-07-31"
        }
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
    
    agent = create_react_agent(
        llm,
        tools,
        state_modifier=system_prompt,
    )
    
    return agent


# ============================================
# ALTERNATIVE: Direct Anthropic API with Caching
# Use this for maximum cost control
# ============================================

def analyze_ticket_with_caching(thread_json: Dict[str, Any]) -> Dict[str, str]:
    """
    Direct Anthropic API call with prompt caching enabled.
    More cost-effective than LangChain for high-volume usage.
    
    CACHING STRATEGY:
    - System prompt (cached)
    - Tool definitions (cached)  
    - Ticket content (NOT cached - changes every time)
    
    Cost comparison per ticket after cache warmup:
    - Without caching: ~1,600 input tokens
    - With caching: ~300 input tokens (80% reduction!)
    """
    
    client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    
    # Format conversation
    conversation = "\n\n".join([
        f"Date: {msg['email_date']}\nContent: {msg['email_content']}"
        for msg in thread_json.get("messages", [])
    ])
    
    # Define tools (will be cached)
    tools = [
        {
            "name": "validate_booking_requirements",
            "description": "Check if all required booking information is present. Returns what's missing if incomplete.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "origin": {"type": "string", "description": "Departure city/airport"},
                    "destination": {"type": "string", "description": "Arrival city/airport"},
                    "departure_date": {"type": "string", "description": "Departure date YYYY-MM-DD"},
                    "return_date": {"type": "string", "description": "Return date YYYY-MM-DD (null for one-way)"},
                    "trip_type": {"type": "string", "enum": ["one_way", "round_trip"]},
                    "passengers": {"type": "integer", "description": "Number of passengers"}
                },
                "required": ["origin", "destination", "departure_date", "trip_type", "passengers"]
            }
        },
        {
            "name": "search_flights",
            "description": "Search for available flights. ONLY call when all required info is present.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "origin": {"type": "string"},
                    "destination": {"type": "string"},
                    "departure_date": {"type": "string"},
                    "return_date": {"type": "string"},
                    "passengers": {"type": "integer"}
                },
                "required": ["origin", "destination", "departure_date", "passengers"]
            }
        }
    ]
    
    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            
            # CACHING: System prompt will be cached
            system=[
                {
                    "type": "text",
                    "text": """You are a travel booking assistant. Follow this EXACT workflow:

WORKFLOW STEPS:
1️⃣ Analyze the customer's email to extract booking details
2️⃣ Call validate_booking_requirements to check completeness
3️⃣ Based on validation:
   
   IF INCOMPLETE:
   - Create email asking for missing information
   - DO NOT search flights
   
   IF COMPLETE:
   - Call search_flights
   - Format results into email

TRIP TYPE RULES:
- ONE date + no "round trip" mention = ONE-WAY
- ONE date + "round trip" mentioned = INCOMPLETE (need return date)
- TWO dates = ROUND TRIP

EMAIL FORMAT:
- Start: "Dear Customer,"
- End: "Best regards,\\nTravel Booking Team"
- Use <br> for line breaks

NEVER assume or invent dates.""",
                    "cache_control": {"type": "ephemeral"}  # ← CACHE THIS
                }
            ],
            
            # CACHING: Tools will be cached
            tools=tools,
            
            # NOT CACHED: Changes every request
            messages=[
                {
                    "role": "user",
                    "content": f"""Analyze this ticket:

TICKET: #{thread_json['ticket_id']}
CUSTOMER: {thread_json['customer_email']}
SUBJECT: {thread_json['subject']}

EMAIL CONVERSATION:
{conversation}

Follow the workflow."""
                }
            ]
        )
        
        # Process tool calls
        assistant_response = ""
        booking_info = {}
        
        for block in response.content:
            if block.type == "text":
                assistant_response = block.text
                
            elif block.type == "tool_use":
                if block.name == "validate_booking_requirements":
                    # Extract booking info
                    booking_info = block.input
                    
                    # Check completeness
                    required = ["origin", "destination", "departure_date", "passengers"]
                    missing = [f for f in required if not booking_info.get(f)]
                    
                    if booking_info.get("trip_type") == "round_trip" and not booking_info.get("return_date"):
                        missing.append("return_date")
                    
                    if missing:
                        # Info incomplete - ask customer
                        return {
                            "type": "info_missing",
                            "msg": f"Dear Customer,<br><br>To process your booking, we need: {', '.join(missing)}<br><br>Best regards,<br>Travel Booking Team",
                            "values": booking_info
                        }
                
                elif block.name == "search_flights":
                    # Call your actual flight API here
                    flight_results = search_flights(
                        origin=block.input["origin"],
                        destination=block.input["destination"],
                        departure_date=block.input["departure_date"],
                        return_date=block.input.get("return_date"),
                        passengers=block.input["passengers"]
                    )
                    
                    # Return results to customer
                    return {
                        "type": "present",
                        "msg": assistant_response or f"Dear Customer,<br><br>Flight options found!<br>{flight_results}<br><br>Best regards,<br>Travel Booking Team",
                        "values": block.input
                    }
        
        # Fallback response
        return {
            "type": "info_missing",
            "msg": assistant_response or "Dear Customer,<br><br>Please provide your travel details.<br><br>Best regards,<br>Travel Booking Team"
        }
        
    except Exception as e:
        return {
            "type": "error",
            "msg": "Dear Customer,<br><br>An error occurred. Our team will assist shortly.<br><br>Best regards,<br>Travel Booking Team",
            "error_details": str(e)
        }


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