from flask import Flask, request, jsonify
from datetime import datetime
from langchain_google_genai import ChatGoogleGenerativeAI
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from asgiref.wsgi import WsgiToAsgi
import os
import logging
import threading
from dotenv import load_dotenv
import jwt
import requests

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)   

# Secure Credentials from .env
MICROSOFT_APP_ID = os.getenv("MICROSOFT_APP_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

EMAIL_SETTINGS = {
    "SMTP_SERVER": os.getenv("SMTP_SERVER"),
    "SMTP_PORT": int(os.getenv("SMTP_PORT", 587)),
    "SENDER_EMAIL": os.getenv("SENDER_EMAIL"),
    "SENDER_PASSWORD": os.getenv("SENDER_PASSWORD")
}

CATEGORIES = {
    "TRAINING_EMAIL": "training@example.com",
    "IT_OPS_EMAIL": "demogptmukund@gmail.com",
    "TECH_EMAIL": "mukunddemochatgpt@gmail.com",
    "HR_EMAIL": "hr@example.com",
    "FINANCE_EMAIL": "finance@example.com",
    "SALES_EMAIL": "sales@example.com"
}

def handle_hi():
    return "👋 Hi! I'm your support assistant. How can I help you today?"

def handle_help():
    return """Available commands:
• Hi - Say hello
• Help - Show this help message
• Create Ticket <description> - Create a new support ticket
• Check Status - Check system status"""

def handle_check_status():
    return "✅ All systems are operational. Ready to assist you!"

def get_department_from_gemini(description):
    """Classify issue into categories using Gemini AI."""
    logger.info(f"Getting department for description: {description}")

    prompt_text = f"""
    You are an AI assistant for a support ticket system. Classify employee issues into one of these categories:
    - Training
    - IT Operations
    - Technology
    - HR
    - Finance
    - Sales

    Description: {description}

    Category:
    """

    try:
        model = ChatGoogleGenerativeAI(model="gemini-pro", api_key=GEMINI_API_KEY, temperature=0.3)
        response = model.invoke(prompt_text)
        category = response.content.strip() if hasattr(response, "content") else str(response).strip()
        return category if category in CATEGORIES else "Training"
    except Exception as e:
        logger.error(f"Error in get_department_from_gemini: {str(e)}")
        return "Training"

def send_notification(subject, body, to_email):
    """Send email notification."""
    logger.info(f"Sending notification to {to_email}")

    msg = MIMEMultipart()
    msg['From'] = EMAIL_SETTINGS['SENDER_EMAIL']
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP(EMAIL_SETTINGS['SMTP_SERVER'], EMAIL_SETTINGS['SMTP_PORT']) as server:
            server.starttls()
            server.login(EMAIL_SETTINGS['SENDER_EMAIL'], EMAIL_SETTINGS['SENDER_PASSWORD'])
            server.send_message(msg)
        logger.info("Notification sent successfully")
        return True
    except Exception as e:
        logger.error(f"Email Error: {str(e)}")
        return False

def process_ticket_async(user_message, user_name, ticket_id):
    """Background function to process the ticket asynchronously."""
    try:
        detected_category = get_department_from_gemini(user_message)
        dept_email = CATEGORIES.get(detected_category, EMAIL_SETTINGS['SENDER_EMAIL'])

        dept_msg = f"""
        New Ticket: {ticket_id}
        Category: {detected_category}
        From: {user_name}
        Description: {user_message}
        """

        send_notification(f"Support Ticket {ticket_id}", dept_msg, dept_email)
        logger.info(f"Ticket {ticket_id} processed successfully!")

    except Exception as e:
        logger.error(f"Error in background processing: {str(e)}")

def verify_teams_request():
    """Verify incoming request is from Teams."""
    try:
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            logger.warning("No Bearer token found")
            return True  # Temporarily allow all requests

        token = auth_header.split(' ')[1]
        
        # Basic token validation
        decoded = jwt.decode(
            token,
            verify=False,  # Skip signature verification for now
            options={'verify_exp': False}
        )
        
        return True
    except Exception as e:
        logger.error(f"Token verification failed: {str(e)}")
        return True  # Temporarily allow all requests

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "healthy",
        "message": "Support Chatbot is running!"
    })

@app.route("/api/messages", methods=["POST"])
def messages():
    """Handle incoming messages from Microsoft Teams."""
    try:
        if not verify_teams_request():
            logger.error("Failed to verify Teams request")
            return jsonify({"error": "Unauthorized"}), 401

        logger.info("Received Teams message")
        data = request.json
        user_message = data.get("text", "").strip()
        user_name = data.get("from", {}).get("name", "Unknown User")

        if not user_message:
            return jsonify({"type": "message", "text": "Please provide a description of your issue."})

        lower_message = user_message.lower()

        if lower_message in ["hi", "hello"]:
            response_text = handle_hi()
        elif lower_message == "help":
            response_text = handle_help()
        elif lower_message == "check status":
            response_text = handle_check_status()
        elif lower_message.startswith("create ticket"):
            description = user_message[13:].strip()
            if not description:
                response_text = "Please provide a description for your ticket."
            else:
                ticket_id = f"TKT-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                threading.Thread(target=process_ticket_async, args=(description, user_name, ticket_id)).start()
                response_text = f"✅ Ticket {ticket_id} has been created. Our support team will get back to you soon!"
        else:
            ticket_id = f"TKT-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            threading.Thread(target=process_ticket_async, args=(user_message, user_name, ticket_id)).start()
            response_text = f"✅ Ticket {ticket_id} is being processed. Our support team will get back to you soon!"

        return jsonify({"type": "message", "text": response_text}), 200

    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        return jsonify({"type": "message", "text": "I encountered an error. Please try again."}), 200

asgi_app = WsgiToAsgi(app)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 5000))
    logger.info(f"Starting server on port {port}")
    uvicorn.run("app:asgi_app", host="0.0.0.0", port=port)
