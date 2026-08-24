import os
import base64
from dotenv import load_dotenv
from openai import OpenAI
from .model import image_system_prompt
from .log_utils import setup_logger

load_dotenv()
logger = setup_logger(__name__)
current_dir = os.getcwd()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def generate_image(thumbnail_file_path, video_title, video_description):
    logger.info("Starting image generation process.")
    input_prompt = image_system_prompt.format(video_title=video_title, video_description=video_description)
    logger.info(f"Input prompt: {input_prompt}")

    image_tool: dict = {
        "type": "image_generation",
        "model": "gpt-image-1-mini",
        "size": "1024x1536",  # Medium size
        "quality": "medium",
        "background": "auto",
        "output_format": "png"
    }

    response = client.responses.create(
        model="gpt-4o-mini",
        input=input_prompt,
        tools=[image_tool],
    )

    # Save the image to a file
    image_data = [
        output.result
        for output in response.output
        if output.type == "image_generation_call"
    ]
    logger.info("Generated image data retrieved.")
    if image_data:
        image_base64 = image_data[0]
        image_path = f"{current_dir}/{thumbnail_file_path}"
        with open(image_path, "wb") as f:
            f.write(base64.b64decode(image_base64))
    return

if __name__ == "__main__":
    generate_image()