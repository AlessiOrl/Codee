import os, pymongo, json, time
import numpy as np

DB_URL = os.environ['DB_URL']
try:
    MAX_RETENTION = int(os.environ['MAX_RETENTION'])
    assert MAX_RETENTION > 0, "MAX_RETENTION must be greater than 0"
except Exception as e:
    print("MAX_RETENTION not set or invalid, using default value of 10")
    MAX_RETENTION = 10

try:
    TOP_K_MESSAGES = int(os.environ['TOP_K_MESSAGES'])
    assert TOP_K_MESSAGES > 0, "TOP_K_MESSAGES must be greater than 0"
    assert TOP_K_MESSAGES <= 100, "TOP_K_MESSAGES must be less than or equal to 100"
except Exception as e:
    print("TOP_K_MESSAGES not set or invalid, using default value of 5")
    TOP_K_MESSAGES = 5


def cosine_similarity(vec1, vec2):
    vec1 = np.array(vec1)
    vec2 = np.array(vec2)
    dot_product = np.dot(vec1, vec2)
    norm_a = np.linalg.norm(vec1)
    norm_b = np.linalg.norm(vec2)
    return dot_product / (norm_a * norm_b)


def calculate_similarity(embedding1, embedding2):
    return float(cosine_similarity(embedding1, embedding2))

def update_chat_history(chat_id, message, response):
    try:
        timsetamp = time.time()
        mongodb_conn = pymongo.MongoClient(f"{DB_URL}/")
        
        # insert the interaction into the database
        llm_user = mongodb_conn[f"User_{chat_id}"]
        llm_chathistory = llm_user[f"ChatHistory"]

        interaction = []
        row = {
            "chat_id": chat_id,
            "role": message["role"],
            "content": message["content"],
            "timestamp": timsetamp,
            "embedding": message["embedding"],
            "metadata": None,
        }
        interaction.append(row)
        row = {
            "chat_id": chat_id,
            "role": response["role"],
            "content": response["content"],
            "timestamp": timsetamp,
            "embedding": response["embedding"],
            "metadata": None,
        }
        interaction.append(row)

        # insert the interaction into the database
        llm_chathistory.insert_many(interaction)
        # close the connection
        mongodb_conn.close()
    except Exception as e:
        print(f"Error updating chat history: {e}")
        return False
    return True

def get_chat_history(chat_id):
    mongodb_conn = pymongo.MongoClient(f"{DB_URL}/")
    llm_user = mongodb_conn[f"User_{chat_id}"]
    llm_chathistory = llm_user[f"ChatHistory"]

    return llm_chathistory, mongodb_conn


def add_context_to_prompt(chat_id, prompt, messages):
    llm_chathistory, mongodb_conn = get_chat_history(chat_id)

    # add <CONTEXT_HISTORY> to the prompt
    query_context = {"chat_id": chat_id}
    recent_x_messages = llm_chathistory.find(query_context).sort("timestamp", pymongo.DESCENDING).limit(200)
    similairies = []
    for message in recent_x_messages:
        similairy = calculate_similarity(user_embedding, message["embedding"])
        # filter out similarities under a certain threshold
        if similairy > 0.9:
            similairies.append({"role": message["role"], "content": message["content"], "similarity": similairy})
    
    # sort the messages by similarity
    similairies.sort(reverse=True, key=lambda x: x["similarity"])
    # get the top x most similar messages
    top_x_similar_messages = similairies[:TOP_K_MESSAGES]

    # add the top 5 messages to the prompt
    messages.append({"role": "system", "content": "Here are some similar messages to your query:\n"})
    for message in top_x_similar_messages:
        messages.append({"role": message["role"] , "content": message["content"]})

    mongodb_conn.close()
    return messages

def add_history_to_prompt(chat_id, prompt, messages):
    llm_chathistory, mongodb_conn = get_chat_history(chat_id)

    # add <TEMPORAL_HISTORY> to the prompt
    # get the last 10 messages 
    query = {"chat_id": chat_id}
    recent_messages = llm_chathistory.find(query).sort("timestamp", pymongo.DESCENDING).limit(MAX_RETENTION)
    # add the messages to the prompt


    messages.append({"role": "system", "content": "Here are the last messages in the conversation:\n"})
    for message in recent_messages:
        messages.append({"role": message["role"] , "content": message["content"]})

    mongodb_conn.close()

def get_prompt(chat_id, user_json:dict):
    user_message = user_json["content"]
    user_embedding = user_json["embedding"]
    messages = []

    # load prompt
    with open("./data/codee_assistant_prompt.txt", "r", encoding="utf-8") as f:
        prompt = f.read()

    # add context to the prompt
    prompt, messages = add_context_to_prompt(chat_id, prompt, messages)
    
    # add history to the prompt
    prompt, messages = add_history_to_prompt(chat_id, prompt, messages)
    
    # add <USER_MESSAGE> to the prompt
    messages.append({"role": "system", "content": "Here is the user Query:\n"})
    messages.append({"role": "user", "content": user_message})

    return prompt, messages