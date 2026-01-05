import time
from dotenv import load_dotenv
from zoho_api import ZohoDeskAPI
from zoho_api import TicketQueueSystem

load_dotenv()

if __name__ == "__main__":
    zoho_api = ZohoDeskAPI()
    queue_system = TicketQueueSystem(zoho_api)

    queue_system.start()

    try:
        print("\n📌 Zoho Desk Ticket Processor running (Ctrl + C to stop)\n")
        while True:
            time.sleep(10)
            print(f"Queue size: {queue_system.ticket_queue.qsize()}")
    except KeyboardInterrupt:
        print("\n🛑 Stopping...")
        queue_system.stop()
        print("Goodbye 👋")
