# Summarization_General_Lib.py
#########################################
# General Summarization Library
# This library is used to perform summarization.
#
####
import configparser
####################
# Function List
#
# 1. extract_text_from_segments(segments: List[Dict]) -> str
# 2. summarize_with_openai(api_key, file_path, custom_prompt_arg)
# 3. summarize_with_anthropic(api_key, file_path, model, custom_prompt_arg, max_retries=3, retry_delay=5)
# 4. summarize_with_cohere(api_key, file_path, model, custom_prompt_arg)
# 5. summarize_with_groq(api_key, file_path, model, custom_prompt_arg)
#
#
####################
# Import necessary libraries
import os
import logging
import time
import requests
import json
from requests import RequestException

from App_Function_Libraries.Audio_Transcription_Lib import convert_to_wav, speech_to_text
from App_Function_Libraries.Chunk_Lib import semantic_chunking, rolling_summarize, recursive_summarize_chunks, \
    improved_chunking_process
from App_Function_Libraries.Diarization_Lib import combine_transcription_and_diarization
from App_Function_Libraries.Local_Summarization_Lib import summarize_with_llama, summarize_with_kobold, \
    summarize_with_oobabooga, summarize_with_tabbyapi, summarize_with_vllm, summarize_with_local_llm
from App_Function_Libraries.SQLite_DB import is_valid_url, add_media_to_database
# Import Local
from App_Function_Libraries.Utils import load_and_log_configs, load_comprehensive_config, sanitize_filename, \
    clean_youtube_url, extract_video_info, create_download_directory
from App_Function_Libraries.Video_DL_Ingestion_Lib import download_video

#
#######################################################################################################################
# Function Definitions
#
config = load_comprehensive_config()
openai_api_key = config.get('API', 'openai_api_key', fallback=None)

def extract_text_from_segments(segments):
    logging.debug(f"Segments received: {segments}")
    logging.debug(f"Type of segments: {type(segments)}")

    text = ""

    if isinstance(segments, list):
        for segment in segments:
            logging.debug(f"Current segment: {segment}")
            logging.debug(f"Type of segment: {type(segment)}")
            if 'Text' in segment:
                text += segment['Text'] + " "
            else:
                logging.warning(f"Skipping segment due to missing 'Text' key: {segment}")
    else:
        logging.warning(f"Unexpected type of 'segments': {type(segments)}")

    return text.strip()


def summarize_with_openai(api_key, input_data, custom_prompt_arg):
    loaded_config_data = load_and_log_configs()
    try:
        # API key validation
        if api_key is None or api_key.strip() == "":
            logging.info("OpenAI: API key not provided as parameter")
            logging.info("OpenAI: Attempting to use API key from config file")
            api_key = loaded_config_data['api_keys']['openai']

        if api_key is None or api_key.strip() == "":
            logging.error("OpenAI: API key not found or is empty")
            return "OpenAI: API Key Not Provided/Found in Config file or is empty"

        logging.debug(f"OpenAI: Using API Key: {api_key[:5]}...{api_key[-5:]}")

        # Input data handling
        logging.debug(f"OpenAI: Raw input data type: {type(input_data)}")
        logging.debug(f"OpenAI: Raw input data (first 500 chars): {str(input_data)[:500]}...")

        if isinstance(input_data, str):
            if input_data.strip().startswith('{'):
                # It's likely a JSON string
                logging.debug("OpenAI: Parsing provided JSON string data for summarization")
                try:
                    data = json.loads(input_data)
                except json.JSONDecodeError as e:
                    logging.error(f"OpenAI: Error parsing JSON string: {str(e)}")
                    return f"OpenAI: Error parsing JSON input: {str(e)}"
            elif os.path.isfile(input_data):
                logging.debug("OpenAI: Loading JSON data from file for summarization")
                with open(input_data, 'r') as file:
                    data = json.load(file)
            else:
                logging.debug("OpenAI: Using provided string data for summarization")
                data = input_data
        else:
            data = input_data

        logging.debug(f"OpenAI: Processed data type: {type(data)}")
        logging.debug(f"OpenAI: Processed data (first 500 chars): {str(data)[:500]}...")

        # Text extraction
        if isinstance(data, dict):
            if 'summary' in data:
                logging.debug("OpenAI: Summary already exists in the loaded data")
                return data['summary']
            elif 'segments' in data:
                text = extract_text_from_segments(data['segments'])
            else:
                text = json.dumps(data)  # Convert dict to string if no specific format
        elif isinstance(data, list):
            text = extract_text_from_segments(data)
        elif isinstance(data, str):
            text = data
        else:
            raise ValueError(f"OpenAI: Invalid input data format: {type(data)}")

        openai_model = loaded_config_data['models']['openai'] or "gpt-4o"
        logging.debug(f"OpenAI: Extracted text (first 500 chars): {text[:500]}...")
        logging.debug(f"OpenAI: Custom prompt: {custom_prompt_arg}")

        openai_model = loaded_config_data['models']['openai'] or "gpt-4o"
        logging.debug(f"OpenAI: Using model: {openai_model}")

        headers = {
            'Authorization': f'Bearer {openai_api_key}',
            'Content-Type': 'application/json'
        }

        logging.debug(
            f"OpenAI API Key: {openai_api_key[:5]}...{openai_api_key[-5:] if openai_api_key else None}")
        logging.debug("openai: Preparing data + prompt for submittal")
        openai_prompt = f"{text} \n\n\n\n{custom_prompt_arg}"
        data = {
            "model": openai_model,
            "messages": [
                {"role": "system", "content": "You are a professional summarizer."},
                {"role": "user", "content": openai_prompt}
            ],
            "max_tokens": 4096,
            "temperature": 0.1
        }

        logging.debug("OpenAI: Posting request")
        response = requests.post('https://api.openai.com/v1/chat/completions', headers=headers, json=data)

        if response.status_code == 200:
            response_data = response.json()
            if 'choices' in response_data and len(response_data['choices']) > 0:
                summary = response_data['choices'][0]['message']['content'].strip()
                logging.debug("OpenAI: Summarization successful")
                logging.debug(f"OpenAI: Summary (first 500 chars): {summary[:500]}...")
                return summary
            else:
                logging.warning("OpenAI: Summary not found in the response data")
                return "OpenAI: Summary not available"
        else:
            logging.error(f"OpenAI: Summarization failed with status code {response.status_code}")
            logging.error(f"OpenAI: Error response: {response.text}")
            return f"OpenAI: Failed to process summary. Status code: {response.status_code}"
    except json.JSONDecodeError as e:
        logging.error(f"OpenAI: Error decoding JSON: {str(e)}", exc_info=True)
        return f"OpenAI: Error decoding JSON input: {str(e)}"
    except requests.RequestException as e:
        logging.error(f"OpenAI: Error making API request: {str(e)}", exc_info=True)
        return f"OpenAI: Error making API request: {str(e)}"
    except Exception as e:
        logging.error(f"OpenAI: Unexpected error: {str(e)}", exc_info=True)
        return f"OpenAI: Unexpected error occurred: {str(e)}"


def summarize_with_anthropic(api_key, input_data, custom_prompt_arg, max_retries=3, retry_delay=5):
    try:
        loaded_config_data = load_and_log_configs()
        # API key validation
        if api_key is None or api_key.strip() == "":
            logging.info("Anthropic: API key not provided as parameter")
            logging.info("Anthropic: Attempting to use API key from config file")
            anthropic_api_key = loaded_config_data['api_keys']['anthropic']

        # Sanity check to ensure API key is not empty in the config file
        if api_key is None or api_key.strip() == "":
            logging.error("Anthropic: API key not found or is empty")
            return "Anthropic: API Key Not Provided/Found in Config file or is empty"

        logging.debug(f"Anthropic: Using API Key: {api_key[:5]}...{api_key[-5:]}")

        if isinstance(input_data, str) and os.path.isfile(input_data):
            logging.debug("AnthropicAI: Loading json data for summarization")
            with open(input_data, 'r') as file:
                data = json.load(file)
        else:
            logging.debug("AnthropicAI: Using provided string data for summarization")
            data = input_data

        # DEBUG - Debug logging to identify sent data
        logging.debug(f"AnthropicAI: Loaded data: {data[:500]}...(snipped to first 500 chars)")
        logging.debug(f"AnthropicAI: Type of data: {type(data)}")

        if isinstance(data, dict) and 'summary' in data:
            # If the loaded data is a dictionary and already contains a summary, return it
            logging.debug("Anthropic: Summary already exists in the loaded data")
            return data['summary']

        # If the loaded data is a list of segment dictionaries or a string, proceed with summarization
        if isinstance(data, list):
            segments = data
            text = extract_text_from_segments(segments)
        elif isinstance(data, str):
            text = data
        else:
            raise ValueError("Anthropic: Invalid input data format")

        anthropic_model = loaded_config_data['models']['anthropic']

        headers = {
            'x-api-key': anthropic_api_key,
            'anthropic-version': '2023-06-01',
            'Content-Type': 'application/json'
        }

        anthropic_prompt = custom_prompt_arg
        logging.debug(f"Anthropic: Prompt is {anthropic_prompt}")
        user_message = {
            "role": "user",
            "content": f"{text} \n\n\n\n{anthropic_prompt}"
        }

        model = loaded_config_data['models']['anthropic']

        data = {
            "model": model,
            "max_tokens": 4096,  # max _possible_ tokens to return
            "messages": [user_message],
            "stop_sequences": ["\n\nHuman:"],
            "temperature": 0.1,
            "top_k": 0,
            "top_p": 1.0,
            "metadata": {
                "user_id": "example_user_id",
            },
            "stream": False,
            "system": "You are a professional summarizer."
        }

        for attempt in range(max_retries):
            try:
                logging.debug("anthropic: Posting request to API")
                response = requests.post('https://api.anthropic.com/v1/messages', headers=headers, json=data)

                # Check if the status code indicates success
                if response.status_code == 200:
                    logging.debug("anthropic: Post submittal successful")
                    response_data = response.json()
                    try:
                        summary = response_data['content'][0]['text'].strip()
                        logging.debug("anthropic: Summarization successful")
                        print("Summary processed successfully.")
                        return summary
                    except (IndexError, KeyError) as e:
                        logging.debug("anthropic: Unexpected data in response")
                        print("Unexpected response format from Anthropic API:", response.text)
                        return None
                elif response.status_code == 500:  # Handle internal server error specifically
                    logging.debug("anthropic: Internal server error")
                    print("Internal server error from API. Retrying may be necessary.")
                    time.sleep(retry_delay)
                else:
                    logging.debug(
                        f"anthropic: Failed to summarize, status code {response.status_code}: {response.text}")
                    print(f"Failed to process summary, status code {response.status_code}: {response.text}")
                    return None

            except RequestException as e:
                logging.error(f"anthropic: Network error during attempt {attempt + 1}/{max_retries}: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    return f"anthropic: Network error: {str(e)}"
    except FileNotFoundError as e:
        logging.error(f"anthropic: File not found: {input_data}")
        return f"anthropic: File not found: {input_data}"
    except json.JSONDecodeError as e:
        logging.error(f"anthropic: Invalid JSON format in file: {input_data}")
        return f"anthropic: Invalid JSON format in file: {input_data}"
    except Exception as e:
        logging.error(f"anthropic: Error in processing: {str(e)}")
        return f"anthropic: Error occurred while processing summary with Anthropic: {str(e)}"


# Summarize with Cohere
def summarize_with_cohere(api_key, input_data, custom_prompt_arg):
    loaded_config_data = load_and_log_configs()
    try:
        # API key validation
        if api_key is None or api_key.strip() == "":
            logging.info("Cohere: API key not provided as parameter")
            logging.info("Cohere: Attempting to use API key from config file")
            api_key = loaded_config_data['api_keys']['cohere']

        if api_key is None or api_key.strip() == "":
            logging.error("Cohere: API key not found or is empty")
            logging.debug(f"Loaded config data: {loaded_config_data}")
            return "Cohere: API Key Not Provided/Found in Config file or is empty"

        logging.debug(f"Cohere: Using API Key: {api_key[:5]}...{api_key[-5:]}")

        if isinstance(input_data, str) and os.path.isfile(input_data):
            logging.debug("Cohere: Loading json data for summarization")
            with open(input_data, 'r') as file:
                data = json.load(file)
        else:
            logging.debug("Cohere: Using provided string data for summarization")
            data = input_data

        # DEBUG - Debug logging to identify sent data
        logging.debug(f"Cohere: Loaded data: {data[:500]}...(snipped to first 500 chars)")
        logging.debug(f"Cohere: Type of data: {type(data)}")

        if isinstance(data, dict) and 'summary' in data:
            # If the loaded data is a dictionary and already contains a summary, return it
            logging.debug("Cohere: Summary already exists in the loaded data")
            return data['summary']

        # If the loaded data is a list of segment dictionaries or a string, proceed with summarization
        if isinstance(data, list):
            segments = data
            text = extract_text_from_segments(segments)
        elif isinstance(data, str):
            text = data
        else:
            raise ValueError("Invalid input data format")

        cohere_model = loaded_config_data['models']['cohere']

        cohere_api_key = api_key

        headers = {
            'accept': 'application/json',
            'content-type': 'application/json',
            'Authorization': f'Bearer {cohere_api_key}'
        }

        cohere_prompt = f"{text} \n\n\n\n{custom_prompt_arg}"
        logging.debug(f"cohere: Prompt being sent is {cohere_prompt}")

        data = {
            "chat_history": [
                {"role": "USER", "message": cohere_prompt}
            ],
            "message": "Please provide a summary.",
            "model": cohere_model,
            "connectors": [{"id": "web-search"}]
        }

        logging.debug("cohere: Submitting request to API endpoint")
        response = requests.post('https://api.cohere.ai/v1/chat', headers=headers, json=data)
        response_data = response.json()
        logging.debug("API Response Data: %s", response_data)

        if response.status_code == 200:
            if 'text' in response_data:
                summary = response_data['text'].strip()
                logging.debug("cohere: Summarization successful")
                print("Summary processed successfully.")
                return summary
            else:
                logging.error("Expected data not found in API response.")
                return "Expected data not found in API response."
        else:
            logging.error(f"cohere: API request failed with status code {response.status_code}: {response.text}")
            print(f"Failed to process summary, status code {response.status_code}: {response.text}")
            return f"cohere: API request failed: {response.text}"

    except Exception as e:
        logging.error("cohere: Error in processing: %s", str(e))
        return f"cohere: Error occurred while processing summary with Cohere: {str(e)}"


# https://console.groq.com/docs/quickstart
def summarize_with_groq(api_key, input_data, custom_prompt_arg):
    loaded_config_data = load_and_log_configs()
    try:
        # API key validation
        if api_key is None or api_key.strip() == "":
            logging.info("Groq: API key not provided as parameter")
            logging.info("Groq: Attempting to use API key from config file")
            api_key = loaded_config_data['api_keys']['groq']

        if api_key is None or api_key.strip() == "":
            logging.error("Groq: API key not found or is empty")
            return "Groq: API Key Not Provided/Found in Config file or is empty"

        logging.debug(f"Groq: Using API Key: {api_key[:5]}...{api_key[-5:]}")

        # Transcript data handling & Validation
        if isinstance(input_data, str) and os.path.isfile(input_data):
            logging.debug("Groq: Loading json data for summarization")
            with open(input_data, 'r') as file:
                data = json.load(file)
        else:
            logging.debug("Groq: Using provided string data for summarization")
            data = input_data

        # DEBUG - Debug logging to identify sent data
        logging.debug(f"Groq: Loaded data: {data[:500]}...(snipped to first 500 chars)")
        logging.debug(f"Groq: Type of data: {type(data)}")

        if isinstance(data, dict) and 'summary' in data:
            # If the loaded data is a dictionary and already contains a summary, return it
            logging.debug("Groq: Summary already exists in the loaded data")
            return data['summary']

        # If the loaded data is a list of segment dictionaries or a string, proceed with summarization
        if isinstance(data, list):
            segments = data
            text = extract_text_from_segments(segments)
        elif isinstance(data, str):
            text = data
        else:
            raise ValueError("Groq: Invalid input data format")

        # Set the model to be used
        groq_model = loaded_config_data['models']['groq']

        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }

        groq_prompt = f"{text} \n\n\n\n{custom_prompt_arg}"
        logging.debug("groq: Prompt being sent is {groq_prompt}")

        data = {
            "messages": [
                {
                    "role": "user",
                    "content": groq_prompt
                }
            ],
            "model": groq_model
        }

        logging.debug("groq: Submitting request to API endpoint")
        print("groq: Submitting request to API endpoint")
        response = requests.post('https://api.groq.com/openai/v1/chat/completions', headers=headers, json=data)

        response_data = response.json()
        logging.debug("API Response Data: %s", response_data)

        if response.status_code == 200:
            if 'choices' in response_data and len(response_data['choices']) > 0:
                summary = response_data['choices'][0]['message']['content'].strip()
                logging.debug("groq: Summarization successful")
                print("Summarization successful.")
                return summary
            else:
                logging.error("Expected data not found in API response.")
                return "Expected data not found in API response."
        else:
            logging.error(f"groq: API request failed with status code {response.status_code}: {response.text}")
            return f"groq: API request failed: {response.text}"

    except Exception as e:
        logging.error("groq: Error in processing: %s", str(e))
        return f"groq: Error occurred while processing summary with groq: {str(e)}"


def summarize_with_openrouter(api_key, input_data, custom_prompt_arg):
    loaded_config_data = load_and_log_configs()
    import requests
    import json
    global openrouter_model, openrouter_api_key
    # API key validation
    if api_key is None or api_key.strip() == "":
        logging.info("OpenRouter: API key not provided as parameter")
        logging.info("OpenRouter: Attempting to use API key from config file")
        openrouter_api_key = loaded_config_data['api_keys']['openrouter']

    if api_key is None or api_key.strip() == "":
        logging.error("OpenRouter: API key not found or is empty")
        return "OpenRouter: API Key Not Provided/Found in Config file or is empty"

    # Model Selection validation
    if openrouter_model is None or openrouter_model.strip() == "":
        logging.info("OpenRouter: model not provided as parameter")
        logging.info("OpenRouter: Attempting to use model from config file")
        openrouter_model = loaded_config_data['api_keys']['openrouter_model']

    if api_key is None or api_key.strip() == "":
        logging.error("OpenAI: API key not found or is empty")
        return "OpenAI: API Key Not Provided/Found in Config file or is empty"

    logging.debug(f"OpenAI: Using API Key: {api_key[:5]}...{api_key[-5:]}")

    logging.debug(f"openai: Using API Key: {api_key[:5]}...{api_key[-5:]}")

    if isinstance(input_data, str) and os.path.isfile(input_data):
        logging.debug("openrouter: Loading json data for summarization")
        with open(input_data, 'r') as file:
            data = json.load(file)
    else:
        logging.debug("openrouter: Using provided string data for summarization")
        data = input_data

    # DEBUG - Debug logging to identify sent data
    logging.debug(f"openrouter: Loaded data: {data[:500]}...(snipped to first 500 chars)")
    logging.debug(f"openrouter: Type of data: {type(data)}")

    if isinstance(data, dict) and 'summary' in data:
        # If the loaded data is a dictionary and already contains a summary, return it
        logging.debug("openrouter: Summary already exists in the loaded data")
        return data['summary']

    # If the loaded data is a list of segment dictionaries or a string, proceed with summarization
    if isinstance(data, list):
        segments = data
        text = extract_text_from_segments(segments)
    elif isinstance(data, str):
        text = data
    else:
        raise ValueError("Invalid input data format")

    config = configparser.ConfigParser()
    file_path = 'config.txt'

    # Check if the file exists in the specified path
    if os.path.exists(file_path):
        config.read(file_path)
    elif os.path.exists('config.txt'):  # Check in the current directory
        config.read('../config.txt')
    else:
        print("config.txt not found in the specified path or current directory.")

    openrouter_prompt = f"{input_data} \n\n\n\n{custom_prompt_arg}"

    try:
        logging.debug("openrouter: Submitting request to API endpoint")
        print("openrouter: Submitting request to API endpoint")
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {openrouter_api_key}",
            },
            data=json.dumps({
                "model": f"{openrouter_model}",
                "messages": [
                    {"role": "user", "content": openrouter_prompt}
                ]
            })
        )

        response_data = response.json()
        logging.debug("API Response Data: %s", response_data)

        if response.status_code == 200:
            if 'choices' in response_data and len(response_data['choices']) > 0:
                summary = response_data['choices'][0]['message']['content'].strip()
                logging.debug("openrouter: Summarization successful")
                print("openrouter: Summarization successful.")
                return summary
            else:
                logging.error("openrouter: Expected data not found in API response.")
                return "openrouter: Expected data not found in API response."
        else:
            logging.error(f"openrouter:  API request failed with status code {response.status_code}: {response.text}")
            return f"openrouter: API request failed: {response.text}"
    except Exception as e:
        logging.error("openrouter: Error in processing: %s", str(e))
        return f"openrouter: Error occurred while processing summary with openrouter: {str(e)}"

def summarize_with_huggingface(api_key, input_data, custom_prompt_arg):
    loaded_config_data = load_and_log_configs()
    global huggingface_api_key
    logging.debug(f"huggingface: Summarization process starting...")
    try:
        # API key validation
        if api_key is None or api_key.strip() == "":
            logging.info("HuggingFace: API key not provided as parameter")
            logging.info("HuggingFace: Attempting to use API key from config file")
            api_key = loaded_config_data['api_keys']['huggingface']

        if api_key is None or api_key.strip() == "":
            logging.error("HuggingFace: API key not found or is empty")
            return "HuggingFace: API Key Not Provided/Found in Config file or is empty"

        logging.debug(f"HuggingFace: Using API Key: {api_key[:5]}...{api_key[-5:]}")

        if isinstance(input_data, str) and os.path.isfile(input_data):
            logging.debug("HuggingFace: Loading json data for summarization")
            with open(input_data, 'r') as file:
                data = json.load(file)
        else:
            logging.debug("HuggingFace: Using provided string data for summarization")
            data = input_data

        # DEBUG - Debug logging to identify sent data
        logging.debug(f"HuggingFace: Loaded data: {data[:500]}...(snipped to first 500 chars)")
        logging.debug(f"HuggingFace: Type of data: {type(data)}")

        if isinstance(data, dict) and 'summary' in data:
            # If the loaded data is a dictionary and already contains a summary, return it
            logging.debug("HuggingFace: Summary already exists in the loaded data")
            return data['summary']

        # If the loaded data is a list of segment dictionaries or a string, proceed with summarization
        if isinstance(data, list):
            segments = data
            text = extract_text_from_segments(segments)
        elif isinstance(data, str):
            text = data
        else:
            raise ValueError("HuggingFace: Invalid input data format")

        print(f"HuggingFace: lets make sure the HF api key exists...\n\t {api_key}")
        headers = {
            "Authorization": f"Bearer {api_key}"
        }

        huggingface_model = loaded_config_data['models']['huggingface']
        API_URL = f"https://api-inference.huggingface.co/models/{huggingface_model}"

        huggingface_prompt = f"{text}\n\n\n\n{custom_prompt_arg}"
        logging.debug("huggingface: Prompt being sent is {huggingface_prompt}")
        data = {
            "inputs": text,
            "parameters": {"max_length": 512, "min_length": 100}  # You can adjust max_length and min_length as needed
        }

        print(f"huggingface: lets make sure the HF api key is the same..\n\t {huggingface_api_key}")

        logging.debug("huggingface: Submitting request...")

        response = requests.post(API_URL, headers=headers, json=data)

        if response.status_code == 200:
            summary = response.json()[0]['summary_text']
            logging.debug("huggingface: Summarization successful")
            print("Summarization successful.")
            return summary
        else:
            logging.error(f"huggingface: Summarization failed with status code {response.status_code}: {response.text}")
            return f"Failed to process summary, status code {response.status_code}: {response.text}"
    except Exception as e:
        logging.error("huggingface: Error in processing: %s", str(e))
        print(f"Error occurred while processing summary with huggingface: {str(e)}")
        return None


def summarize_with_deepseek(api_key, input_data, custom_prompt_arg):
    loaded_config_data = load_and_log_configs()
    try:
        # API key validation
        if api_key is None or api_key.strip() == "":
            logging.info("DeepSeek: API key not provided as parameter")
            logging.info("DeepSeek: Attempting to use API key from config file")
            api_key = loaded_config_data['api_keys']['deepseek']

        if api_key is None or api_key.strip() == "":
            logging.error("DeepSeek: API key not found or is empty")
            return "DeepSeek: API Key Not Provided/Found in Config file or is empty"

        logging.debug(f"DeepSeek: Using API Key: {api_key[:5]}...{api_key[-5:]}")

        # Input data handling
        if isinstance(input_data, str) and os.path.isfile(input_data):
            logging.debug("DeepSeek: Loading json data for summarization")
            with open(input_data, 'r') as file:
                data = json.load(file)
        else:
            logging.debug("DeepSeek: Using provided string data for summarization")
            data = input_data

        # DEBUG - Debug logging to identify sent data
        logging.debug(f"DeepSeek: Loaded data: {data[:500]}...(snipped to first 500 chars)")
        logging.debug(f"DeepSeek: Type of data: {type(data)}")

        if isinstance(data, dict) and 'summary' in data:
            # If the loaded data is a dictionary and already contains a summary, return it
            logging.debug("DeepSeek: Summary already exists in the loaded data")
            return data['summary']

        # Text extraction
        if isinstance(data, list):
            segments = data
            text = extract_text_from_segments(segments)
        elif isinstance(data, str):
            text = data
        else:
            raise ValueError("DeepSeek: Invalid input data format")

        deepseek_model = loaded_config_data['models']['deepseek'] or "deepseek-chat"

        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }

        logging.debug(
            f"Deepseek API Key: {api_key[:5]}...{api_key[-5:] if api_key else None}")
        logging.debug("openai: Preparing data + prompt for submittal")
        deepseek_prompt = f"{text} \n\n\n\n{custom_prompt_arg}"
        data = {
            "model": deepseek_model,
            "messages": [
                {"role": "system", "content": "You are a professional summarizer."},
                {"role": "user", "content": deepseek_prompt}
            ],
            "stream": False,
            "temperature": 0.8
        }

        logging.debug("DeepSeek: Posting request")
        response = requests.post('https://api.deepseek.com/chat/completions', headers=headers, json=data)

        if response.status_code == 200:
            response_data = response.json()
            if 'choices' in response_data and len(response_data['choices']) > 0:
                summary = response_data['choices'][0]['message']['content'].strip()
                logging.debug("DeepSeek: Summarization successful")
                return summary
            else:
                logging.warning("DeepSeek: Summary not found in the response data")
                return "DeepSeek: Summary not available"
        else:
            logging.error(f"DeepSeek: Summarization failed with status code {response.status_code}")
            logging.error(f"DeepSeek: Error response: {response.text}")
            return f"DeepSeek: Failed to process summary. Status code: {response.status_code}"
    except Exception as e:
        logging.error(f"DeepSeek: Error in processing: {str(e)}", exc_info=True)
        return f"DeepSeek: Error occurred while processing summary: {str(e)}"


#
#
#######################################################################################################################
#
#
# Gradio File Processing


# Handle multiple videos as input
def process_video_urls(url_list, num_speakers, whisper_model, custom_prompt_input, offset, api_name, api_key, vad_filter,
                       download_video_flag, download_audio, rolling_summarization, detail_level, question_box,
                       keywords, chunk_text_by_words, max_words, chunk_text_by_sentences, max_sentences,
                       chunk_text_by_paragraphs, max_paragraphs, chunk_text_by_tokens, max_tokens,  chunk_by_semantic,
                       semantic_chunk_size, semantic_chunk_overlap, recursive_summarization):
    global current_progress
    progress = []  # This must always be a list
    status = []  # This must always be a list

    if custom_prompt_input is None:
        custom_prompt_input = """
            You are a bulleted notes specialist. ```When creating comprehensive bulleted notes, you should follow these guidelines: Use multiple headings based on the referenced topics, not categories like quotes or terms. Headings should be surrounded by bold formatting and not be listed as bullet points themselves. Leave no space between headings and their corresponding list items underneath. Important terms within the content should be emphasized by setting them in bold font. Any text that ends with a colon should also be bolded. Before submitting your response, review the instructions, and make any corrections necessary to adhered to the specified format. Do not reference these instructions within the notes.``` \nBased on the content between backticks create comprehensive bulleted notes.
    **Bulleted Note Creation Guidelines**

    **Headings**:
    - Based on referenced topics, not categories like quotes or terms
    - Surrounded by **bold** formatting 
    - Not listed as bullet points
    - No space between headings and list items underneath

    **Emphasis**:
    - **Important terms** set in bold font
    - **Text ending in a colon**: also bolded

    **Review**:
    - Ensure adherence to specified format
    - Do not reference these instructions in your response.</s>[INST] {{ .Prompt }} [/INST]"""

    def update_progress(index, url, message):
        progress.append(f"Processing {index + 1}/{len(url_list)}: {url}")  # Append to list
        status.append(message)  # Append to list
        return "\n".join(progress), "\n".join(status)  # Return strings for display


    for index, url in enumerate(url_list):
        try:
            logging.info(f"Starting to process video {index + 1}/{len(url_list)}: {url}")
            transcription, summary, json_file_path, summary_file_path, _, _ = process_url(
                url=url,
                num_speakers=num_speakers,
                whisper_model=whisper_model,
                custom_prompt_input=custom_prompt_input,
                offset=offset,
                api_name=api_name,
                api_key=api_key,
                vad_filter=vad_filter,
                download_video_flag=download_video_flag,
                download_audio=download_audio,
                rolling_summarization=rolling_summarization,
                detail_level=detail_level,
                question_box=question_box,
                keywords=keywords,
                chunk_text_by_words=chunk_text_by_words,
                max_words=max_words,
                chunk_text_by_sentences=chunk_text_by_sentences,
                max_sentences=max_sentences,
                chunk_text_by_paragraphs=chunk_text_by_paragraphs,
                max_paragraphs=max_paragraphs,
                chunk_text_by_tokens=chunk_text_by_tokens,
                max_tokens=max_tokens,
                chunk_by_semantic=chunk_by_semantic,
                semantic_chunk_size=semantic_chunk_size,
                semantic_chunk_overlap=semantic_chunk_overlap,
                recursive_summarization=recursive_summarization
            )
            # Update progress and transcription properly

            current_progress, current_status = update_progress(index, url, "Video processed and ingested into the database.")
            logging.info(f"Successfully processed video {index + 1}/{len(url_list)}: {url}")

            time.sleep(1)
        except Exception as e:
            logging.error(f"Error processing video {index + 1}/{len(url_list)}: {url}")
            logging.error(f"Error details: {str(e)}")
            current_progress, current_status = update_progress(index, url, f"Error: {str(e)}")

        yield current_progress, current_status, None, None, None, None

    success_message = "All videos have been transcribed, summarized, and ingested into the database successfully."
    return current_progress, success_message, None, None, None, None


# stuff
def perform_transcription(video_path, offset, whisper_model, vad_filter, diarize=False):
    global segments_json_path
    audio_file_path = convert_to_wav(video_path, offset)
    segments_json_path = audio_file_path.replace('.wav', '.segments.json')

    if diarize:
        diarized_json_path = audio_file_path.replace('.wav', '.diarized.json')

        # Check if diarized JSON already exists
        if os.path.exists(diarized_json_path):
            logging.info(f"Diarized file already exists: {diarized_json_path}")
            try:
                with open(diarized_json_path, 'r') as file:
                    diarized_segments = json.load(file)
                if not diarized_segments:
                    logging.warning(f"Diarized JSON file is empty, re-generating: {diarized_json_path}")
                    raise ValueError("Empty diarized JSON file")
                logging.debug(f"Loaded diarized segments from {diarized_json_path}")
                return audio_file_path, diarized_segments
            except (json.JSONDecodeError, ValueError) as e:
                logging.error(f"Failed to read or parse the diarized JSON file: {e}")
                os.remove(diarized_json_path)

        # If diarized file doesn't exist or was corrupted, generate new diarized transcription
        logging.info(f"Generating diarized transcription for {audio_file_path}")
        diarized_segments = combine_transcription_and_diarization(audio_file_path)

        # Save diarized segments
        with open(diarized_json_path, 'w') as file:
            json.dump(diarized_segments, file, indent=2)

        return audio_file_path, diarized_segments

    # Non-diarized transcription (existing functionality)
    if os.path.exists(segments_json_path):
        logging.info(f"Segments file already exists: {segments_json_path}")
        try:
            with open(segments_json_path, 'r') as file:
                segments = json.load(file)
            if not segments:
                logging.warning(f"Segments JSON file is empty, re-generating: {segments_json_path}")
                raise ValueError("Empty segments JSON file")
            logging.debug(f"Loaded segments from {segments_json_path}")
        except (json.JSONDecodeError, ValueError) as e:
            logging.error(f"Failed to read or parse the segments JSON file: {e}")
            os.remove(segments_json_path)
            logging.info(f"Re-generating transcription for {audio_file_path}")
            audio_file, segments = re_generate_transcription(audio_file_path, whisper_model, vad_filter)
            if segments is None:
                return None, None
    else:
        audio_file, segments = re_generate_transcription(audio_file_path, whisper_model, vad_filter)

    return audio_file_path, segments


def re_generate_transcription(audio_file_path, whisper_model, vad_filter):
    try:
        segments = speech_to_text(audio_file_path, whisper_model=whisper_model, vad_filter=vad_filter)
        # Save segments to JSON
        with open(segments_json_path, 'w') as file:
            json.dump(segments, file, indent=2)
        logging.debug(f"Transcription segments saved to {segments_json_path}")
        return audio_file_path, segments
    except Exception as e:
        logging.error(f"Error in re-generating transcription: {str(e)}")
        return None, None


def save_transcription_and_summary(transcription_text, summary_text, download_path, info_dict):
    try:
        video_title = sanitize_filename(info_dict.get('title', 'Untitled'))

        # Save transcription
        transcription_file_path = os.path.join(download_path, f"{video_title}_transcription.txt")
        with open(transcription_file_path, 'w', encoding='utf-8') as f:
            f.write(transcription_text)

        # Save summary if available
        summary_file_path = None
        if summary_text:
            summary_file_path = os.path.join(download_path, f"{video_title}_summary.txt")
            with open(summary_file_path, 'w', encoding='utf-8') as f:
                f.write(summary_text)

        return transcription_file_path, summary_file_path
    except Exception as e:
        logging.error(f"Error in save_transcription_and_summary: {str(e)}", exc_info=True)
        return None, None


def summarize_chunk(api_name, text, custom_prompt_input, api_key):
    try:
        if api_name.lower() == 'openai':
            return summarize_with_openai(api_key, text, custom_prompt_input)
        elif api_name.lower() == "anthropic":
            return summarize_with_anthropic(api_key, text, custom_prompt_input)
        elif api_name.lower() == "cohere":
            return summarize_with_cohere(api_key, text, custom_prompt_input)
        elif api_name.lower() == "groq":
            return summarize_with_groq(api_key, text, custom_prompt_input)
        elif api_name.lower() == "openrouter":
            return summarize_with_openrouter(api_key, text, custom_prompt_input)
        elif api_name.lower() == "deepseek":
            return summarize_with_deepseek(api_key, text, custom_prompt_input)
        elif api_name.lower() == "llama.cpp":
            return summarize_with_llama(text, custom_prompt_input)
        elif api_name.lower() == "kobold":
            return summarize_with_kobold(text, api_key, custom_prompt_input)
        elif api_name.lower() == "ooba":
            return summarize_with_oobabooga(text, api_key, custom_prompt_input)
        elif api_name.lower() == "tabbyapi":
            return summarize_with_tabbyapi(text, custom_prompt_input)
        elif api_name.lower() == "vllm":
            return summarize_with_vllm(text, custom_prompt_input)
        elif api_name.lower() == "local-llm":
            return summarize_with_local_llm(text, custom_prompt_input)
        elif api_name.lower() == "huggingface":
            return summarize_with_huggingface(api_key, text, custom_prompt_input)
        else:
            logging.warning(f"Unsupported API: {api_name}")
            return None
    except Exception as e:
        logging.error(f"Error in summarize_chunk with {api_name}: {str(e)}")
        return None


def extract_metadata_and_content(input_data):
    metadata = {}
    content = ""

    if isinstance(input_data, str):
        if os.path.exists(input_data):
            with open(input_data, 'r', encoding='utf-8') as file:
                data = json.load(file)
        else:
            try:
                data = json.loads(input_data)
            except json.JSONDecodeError:
                return {}, input_data
    elif isinstance(input_data, dict):
        data = input_data
    else:
        return {}, str(input_data)

    # Extract metadata
    metadata['title'] = data.get('title', 'No title available')
    metadata['author'] = data.get('author', 'Unknown author')

    # Extract content
    if 'transcription' in data:
        content = extract_text_from_segments(data['transcription'])
    elif 'segments' in data:
        content = extract_text_from_segments(data['segments'])
    elif 'content' in data:
        content = data['content']
    else:
        content = json.dumps(data)

    return metadata, content


def format_input_with_metadata(metadata, content):
    formatted_input = f"Title: {metadata.get('title', 'No title available')}\n"
    formatted_input += f"Author: {metadata.get('author', 'Unknown author')}\n\n"
    formatted_input += content
    return formatted_input

def perform_summarization(api_name, input_data, custom_prompt_input, api_key, recursive_summarization=False):
    loaded_config_data = load_and_log_configs()
    logging.info("Starting summarization process...")
    if custom_prompt_input is None:
        custom_prompt_input = """
        You are a bulleted notes specialist. ```When creating comprehensive bulleted notes, you should follow these guidelines: Use multiple headings based on the referenced topics, not categories like quotes or terms. Headings should be surrounded by bold formatting and not be listed as bullet points themselves. Leave no space between headings and their corresponding list items underneath. Important terms within the content should be emphasized by setting them in bold font. Any text that ends with a colon should also be bolded. Before submitting your response, review the instructions, and make any corrections necessary to adhered to the specified format. Do not reference these instructions within the notes.``` \nBased on the content between backticks create comprehensive bulleted notes.
**Bulleted Note Creation Guidelines**

**Headings**:
- Based on referenced topics, not categories like quotes or terms
- Surrounded by **bold** formatting 
- Not listed as bullet points
- No space between headings and list items underneath

**Emphasis**:
- **Important terms** set in bold font
- **Text ending in a colon**: also bolded

**Review**:
- Ensure adherence to specified format
- Do not reference these instructions in your response.</s>[INST] {{ .Prompt }} [/INST]"""

    try:
        logging.debug(f"Input data type: {type(input_data)}")
        logging.debug(f"Input data (first 500 chars): {str(input_data)[:500]}...")

        # Extract metadata and content
        metadata, content = extract_metadata_and_content(input_data)

        logging.debug(f"Extracted metadata: {metadata}")
        logging.debug(f"Extracted content (first 500 chars): {content[:500]}...")

        # Prepare a structured input for summarization
        structured_input = format_input_with_metadata(metadata, content)

        # Perform summarization on the structured input
        if recursive_summarization:
            chunk_options = {
                'method': 'words',  # or 'sentences', 'paragraphs', 'tokens' based on your preference
                'max_size': 1000,  # adjust as needed
                'overlap': 100,  # adjust as needed
                'adaptive': False,
                'multi_level': False,
                'language': 'english'
            }
            chunks = improved_chunking_process(structured_input, chunk_options)
            summary = recursive_summarize_chunks([chunk['text'] for chunk in chunks],
                                                 lambda x: summarize_chunk(api_name, x, custom_prompt_input, api_key),
                                                 custom_prompt_input)
        else:
            summary = summarize_chunk(api_name, structured_input, custom_prompt_input, api_key)

        if summary:
            logging.info(f"Summary generated using {api_name} API")
            if isinstance(input_data, str) and os.path.exists(input_data):
                summary_file_path = input_data.replace('.json', '_summary.txt')
                with open(summary_file_path, 'w', encoding='utf-8') as file:
                    file.write(summary)
        else:
            logging.warning(f"Failed to generate summary using {api_name} API")

        logging.info("Summarization completed successfully.")

        return summary

    except requests.exceptions.ConnectionError:
        logging.error("Connection error while summarizing")
    except Exception as e:
        logging.error(f"Error summarizing with {api_name}: {str(e)}", exc_info=True)
        return f"An error occurred during summarization: {str(e)}"
    return None

def extract_text_from_input(input_data):
    if isinstance(input_data, str):
        try:
            # Try to parse as JSON
            data = json.loads(input_data)
        except json.JSONDecodeError:
            # If not valid JSON, treat as plain text
            return input_data
    elif isinstance(input_data, dict):
        data = input_data
    else:
        return str(input_data)

    # Extract relevant fields from the JSON object
    text_parts = []
    if 'title' in data:
        text_parts.append(f"Title: {data['title']}")
    if 'description' in data:
        text_parts.append(f"Description: {data['description']}")
    if 'transcription' in data:
        if isinstance(data['transcription'], list):
            transcription_text = ' '.join([segment.get('Text', '') for segment in data['transcription']])
        elif isinstance(data['transcription'], str):
            transcription_text = data['transcription']
        else:
            transcription_text = str(data['transcription'])
        text_parts.append(f"Transcription: {transcription_text}")
    elif 'segments' in data:
        segments_text = extract_text_from_segments(data['segments'])
        text_parts.append(f"Segments: {segments_text}")

    return '\n\n'.join(text_parts)



def process_url(
        url,
        num_speakers,
        whisper_model,
        custom_prompt_input,
        offset,
        api_name,
        api_key,
        vad_filter,
        download_video_flag,
        download_audio,
        rolling_summarization,
        detail_level,
        # It's for the asking a question about a returned prompt - needs to be removed #FIXME
        question_box,
        keywords,
        chunk_text_by_words,
        max_words,
        chunk_text_by_sentences,
        max_sentences,
        chunk_text_by_paragraphs,
        max_paragraphs,
        chunk_text_by_tokens,
        max_tokens,
        chunk_by_semantic,
        semantic_chunk_size,
        semantic_chunk_overlap,
        local_file_path=None,
        diarize=False,
        recursive_summarization=False
):
    # Handle the chunk summarization options
    set_chunk_txt_by_words = chunk_text_by_words
    set_max_txt_chunk_words = max_words
    set_chunk_txt_by_sentences = chunk_text_by_sentences
    set_max_txt_chunk_sentences = max_sentences
    set_chunk_txt_by_paragraphs = chunk_text_by_paragraphs
    set_max_txt_chunk_paragraphs = max_paragraphs
    set_chunk_txt_by_tokens = chunk_text_by_tokens
    set_max_txt_chunk_tokens = max_tokens
    set_chunk_txt_by_semantic = chunk_by_semantic
    set_semantic_chunk_size = semantic_chunk_size
    set_semantic_chunk_overlap = semantic_chunk_overlap

    progress = []
    success_message = "All videos processed successfully. Transcriptions and summaries have been ingested into the database."

    if custom_prompt_input is None:
        custom_prompt_input = """
            You are a bulleted notes specialist. ```When creating comprehensive bulleted notes, you should follow these guidelines: Use multiple headings based on the referenced topics, not categories like quotes or terms. Headings should be surrounded by bold formatting and not be listed as bullet points themselves. Leave no space between headings and their corresponding list items underneath. Important terms within the content should be emphasized by setting them in bold font. Any text that ends with a colon should also be bolded. Before submitting your response, review the instructions, and make any corrections necessary to adhered to the specified format. Do not reference these instructions within the notes.``` \nBased on the content between backticks create comprehensive bulleted notes.
    **Bulleted Note Creation Guidelines**

    **Headings**:
    - Based on referenced topics, not categories like quotes or terms
    - Surrounded by **bold** formatting 
    - Not listed as bullet points
    - No space between headings and list items underneath

    **Emphasis**:
    - **Important terms** set in bold font
    - **Text ending in a colon**: also bolded

    **Review**:
    - Ensure adherence to specified format
    - Do not reference these instructions in your response.</s>[INST] {{ .Prompt }} [/INST]"""

    # Validate input
    if not url and not local_file_path:
        return "Process_URL: No URL provided.", "No URL provided.", None, None, None, None, None, None

    # FIXME - Chatgpt again?
    if isinstance(url, str):
        urls = url.strip().split('\n')
        if len(urls) > 1:
            return process_video_urls(urls, num_speakers, whisper_model, custom_prompt_input, offset, api_name, api_key, vad_filter,
                                      download_video_flag, download_audio, rolling_summarization, detail_level, question_box,
                                      keywords, chunk_text_by_words, max_words, chunk_text_by_sentences, max_sentences,
                                      chunk_text_by_paragraphs, max_paragraphs, chunk_text_by_tokens, max_tokens, chunk_by_semantic, semantic_chunk_size, semantic_chunk_overlap)
        else:
            urls = [url]

    if url and not is_valid_url(url):
        return "Process_URL: Invalid URL format.", "Invalid URL format.", None, None, None, None, None, None

    if url:
        # Clean the URL to remove playlist parameters if any
        url = clean_youtube_url(url)
        logging.info(f"Process_URL: Processing URL: {url}")

    if api_name:
        print("Process_URL: API Name received:", api_name)  # Debugging line

    video_file_path = None
    global info_dict

    # If URL/Local video file is provided
    try:
        info_dict, title = extract_video_info(url)
        download_path = create_download_directory(title)
        video_path = download_video(url, download_path, info_dict, download_video_flag)
        global segments
        audio_file_path, segments = perform_transcription(video_path, offset, whisper_model, vad_filter)

        if diarize:
            transcription_text = combine_transcription_and_diarization(audio_file_path)
        else:
            audio_file, segments = perform_transcription(video_path, offset, whisper_model, vad_filter)
            transcription_text = {'audio_file': audio_file, 'transcription': segments}


        if audio_file_path is None or segments is None:
            logging.error("Process_URL: Transcription failed or segments not available.")
            return "Process_URL: Transcription failed.", "Transcription failed.", None, None, None, None

        logging.debug(f"Process_URL: Transcription audio_file: {audio_file_path}")
        logging.debug(f"Process_URL: Transcription segments: {segments}")

        logging.debug(f"Process_URL: Transcription text: {transcription_text}")

        # FIXME - Implement chunking calls here
        # Implement chunking calls here
        chunked_transcriptions = []
        if chunk_text_by_words:
            chunked_transcriptions = chunk_text_by_words(transcription_text['transcription'], max_words)
        elif chunk_text_by_sentences:
            chunked_transcriptions = chunk_text_by_sentences(transcription_text['transcription'], max_sentences)
        elif chunk_text_by_paragraphs:
            chunked_transcriptions = chunk_text_by_paragraphs(transcription_text['transcription'], max_paragraphs)
        elif chunk_text_by_tokens:
            chunked_transcriptions = chunk_text_by_tokens(transcription_text['transcription'], max_tokens)
        elif chunk_by_semantic:
            chunked_transcriptions = semantic_chunking(transcription_text['transcription'], semantic_chunk_size, 'tokens')

        # If we did chunking, we now have the chunked transcripts in 'chunked_transcriptions'
        elif rolling_summarization:
        # FIXME - rolling summarization
        #     text = extract_text_from_segments(segments)
        #     summary_text = rolling_summarize_function(
        #         transcription_text,
        #         detail=detail_level,
        #         api_name=api_name,
        #         api_key=api_key,
        #         custom_prompt_input=custom_prompt_input,
        #         chunk_by_words=chunk_text_by_words,
        #         max_words=max_words,
        #         chunk_by_sentences=chunk_text_by_sentences,
        #         max_sentences=max_sentences,
        #         chunk_by_paragraphs=chunk_text_by_paragraphs,
        #         max_paragraphs=max_paragraphs,
        #         chunk_by_tokens=chunk_text_by_tokens,
        #         max_tokens=max_tokens
        #     )
            pass
        else:
            pass

        summarized_chunk_transcriptions = []

        if chunk_text_by_words or chunk_text_by_sentences or chunk_text_by_paragraphs or chunk_text_by_tokens or chunk_by_semantic and api_name:
            # Perform summarization based on chunks
            for chunk in chunked_transcriptions:
                summarized_chunks = []
                if api_name == "anthropic":
                    summary = summarize_with_anthropic(api_key, chunk, custom_prompt_input)
                elif api_name == "cohere":
                    summary = summarize_with_cohere(api_key, chunk, custom_prompt_input)
                elif api_name == "openai":
                    summary = summarize_with_openai(api_key, chunk, custom_prompt_input)
                elif api_name == "Groq":
                    summary = summarize_with_groq(api_key, chunk, custom_prompt_input)
                elif api_name == "DeepSeek":
                    summary = summarize_with_deepseek(api_key, chunk, custom_prompt_input)
                elif api_name == "OpenRouter":
                    summary = summarize_with_openrouter(api_key, chunk, custom_prompt_input)
                elif api_name == "Llama.cpp":
                    summary = summarize_with_llama(chunk, custom_prompt_input)
                elif api_name == "Kobold":
                    summary = summarize_with_kobold(chunk, custom_prompt_input)
                elif api_name == "Ooba":
                    summary = summarize_with_oobabooga(chunk, custom_prompt_input)
                elif api_name == "Tabbyapi":
                    summary = summarize_with_tabbyapi(chunk, custom_prompt_input)
                elif api_name == "VLLM":
                    summary = summarize_with_vllm(chunk, custom_prompt_input)
                summarized_chunk_transcriptions.append(summary)

        # Combine chunked transcriptions into a single file
        combined_transcription_text = '\n\n'.join(chunked_transcriptions)
        combined_transcription_file_path = os.path.join(download_path, 'combined_transcription.txt')
        with open(combined_transcription_file_path, 'w') as f:
            f.write(combined_transcription_text)

        # Combine summarized chunk transcriptions into a single file
        combined_summary_text = '\n\n'.join(summarized_chunk_transcriptions)
        combined_summary_file_path = os.path.join(download_path, 'combined_summary.txt')
        with open(combined_summary_file_path, 'w') as f:
            f.write(combined_summary_text)

        # Handle rolling summarization
        if rolling_summarization:
            summary_text = rolling_summarize(
                text=extract_text_from_segments(segments),
                detail=detail_level,
                model='gpt-4-turbo',
                additional_instructions=custom_prompt_input,
                summarize_recursively=recursive_summarization
            )
        elif api_name:
            summary_text = perform_summarization(api_name, segments_json_path, custom_prompt_input, api_key,
                                                 recursive_summarization)
        else:
            summary_text = 'Summary not available'

        # Check to see if chunking was performed, and if so, return that instead
        if chunk_text_by_words or chunk_text_by_sentences or chunk_text_by_paragraphs or chunk_text_by_tokens or chunk_by_semantic:
            # Combine chunked transcriptions into a single file
            # FIXME - validate this works....
            json_file_path, summary_file_path = save_transcription_and_summary(combined_transcription_file_path, combined_summary_file_path, download_path)
            add_media_to_database(url, info_dict, segments, summary_text, keywords, custom_prompt_input, whisper_model)
            return transcription_text, summary_text, json_file_path, summary_file_path, None, None
        else:
            json_file_path, summary_file_path = save_transcription_and_summary(transcription_text, summary_text, download_path)
            add_media_to_database(url, info_dict, segments, summary_text, keywords, custom_prompt_input, whisper_model)
            return transcription_text, summary_text, json_file_path, summary_file_path, None, None

    except Exception as e:
        logging.error(f": {e}")
        return str(e), 'process_url: Error processing the request.', None, None, None, None

#
#
############################################################################################################################################
