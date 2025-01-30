import os

os.environ["ANONYMIZED_TELEMETRY"] = "false"

from langchain_google_genai import ChatGoogleGenerativeAI
from browser_use import Agent, Browser, BrowserConfig, SystemPrompt
from dotenv import load_dotenv
from pydantic import SecretStr, BaseModel
from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.security import APIKeyHeader
from typing import Optional
load_dotenv()
import asyncio
import uvicorn
import uuid

chrome_path = 'C:\\Users\\User\\AppData\\Local\\Google\\Chrome SxS\\Application\\chrome.exe' # path to the isolated Chrome instance
gemini_api_key = SecretStr('') # Google AI Studio API key
delivery_address = "UK, London SW1A 1AA, Buckingham Palace. If you see 'City of Westminster', it refers to the correct address"
dietary_restrictions = "Ensure that you order only pescetarian food (not containing meat; can contain fish, dairy, plants)."

# API configuration
app = FastAPI()
API_KEY = os.getenv("API_KEY", "api-key")  # Set this in .env
api_key_header = APIKeyHeader(name="X-API-Key")

# Request model
class TaskRequest(BaseModel):
    task: str

class TaskStatus(BaseModel):
    id: str
    status: str
    result: Optional[str] = None

# Store for task results
task_store = {}

async def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key

class FoodOrderingSystemPrompt(SystemPrompt):
    def important_rules(self) -> str:
        # Get existing rules from parent class
        existing_rules = super().important_rules()

        # Add your custom rules
        new_rules = """
9. MOST IMPORTANT RULE:
- Always close popups and clear search terms if you completed the search or no longer need the popup.
- The delivery address is {delivery_address}. The default address is correct. Reuse the default address.
- At order review/checkout, scroll down and click on Place the order.
- The task is only complete when you see that the order is confirmed.
- In case of any issues, come back to search. The order should only contain what the user asked you to order.
- Search in Groceries or Restaraunts depending on the user request.
- If a user wants food from a restaraunt, ensure it's cooked food and not a grocery store food that needs preparation.
- Ensure you only order exactly what the user asked you to order and nothing else. {dietary_restrictions}
"""

        # Make sure to use this pattern otherwise the exiting rules will be lost
        return f'{existing_rules}\n{new_rules}'

@app.post("/run-task")
async def run_task(task_request: TaskRequest, api_key: str = Depends(verify_api_key)):
    # Generate a task ID
    task_id = str(uuid.uuid4())
    
    # Start task in background
    asyncio.create_task(process_task(task_id, task_request.task))
    
    # Return immediately with task ID
    return {"status": "accepted", "task_id": task_id}

@app.get("/task-status/{task_id}")
async def get_task_status(task_id: str, api_key: str = Depends(verify_api_key)):
    if task_id not in task_store:
        raise HTTPException(status_code=404, detail="Task not found")
    return task_store[task_id]

async def process_task(task_id: str, task: str):
    try:
        task_store[task_id] = TaskStatus(id=task_id, status="running")
        
        # Initialize components for the request
        llm = ChatGoogleGenerativeAI(model='gemini-2.0-flash-exp', api_key=gemini_api_key)
        
        config = BrowserConfig(
            chrome_instance_path=chrome_path
        )
        
        browser = Browser(config=config)
        
        agent = Agent(
            browser=browser,
            task=task,
            llm=llm,
            use_vision=True,
            system_prompt_class=FoodOrderingSystemPrompt
        )

        result = await agent.run()
        await browser.close()
        
        # Convert the result to string if it's not already
        result_str = str(result) if result is not None else "Task completed without result"
        
        task_store[task_id] = TaskStatus(
            id=task_id, 
            status="completed", 
            result=result_str
        )
        
    except Exception as e:
        await browser.close()
        task_store[task_id] = TaskStatus(
            id=task_id, 
            status="failed", 
            result=f"Error: {str(e)}"
        )

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
