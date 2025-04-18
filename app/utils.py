import os, pymongo, json, time

DB_URL = os.environ['DB_URL']

def calculate_similarity(message1, message2):
    # Placeholder for actual similarity calculation
    # For now, we will just return a dummy value
    return 0.2

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

def get_prompt(chat_id, completion, user_message):
    # connect to the database
    llm_chathistory, mongodb_conn = get_chat_history(chat_id)

    # load prompt
    with open("./data/codee_assistant_prompt.txt", "r", encoding="utf-8") as f:
        prompt = f.read()

    # add <CONTEXT_HISTORY> to the prompt
    query_context = {"chat_id": chat_id}
    recent_100_messages = llm_chathistory.find(query_context).sort("timestamp", pymongo.DESCENDING).limit(100)
    similairies = []
    for message in recent_100_messages:
        similairy = calculate_similarity(message["content"], user_message)
        # filter out similarities under a certain threshold
        if similairy > 0.2:
            similairies.append({"role": message["role"], "content": message["content"], "similarity": similairy})
    # sort the messages by similarity
    similairies.sort(reverse=True)
    # get the top 5 most similar messages
    top_5_similar_messages = similairies[:5]

    # add the top 5 messages to the prompt
    meta_prompt = ""
    for message in top_5_similar_messages:
        meta_prompt += message["role"] + ": " + message["content"] + "\n"

    if meta_prompt == "":
        meta_prompt = "No similar messages found.\n"

    # add the meta prompt to the prompt
    prompt = prompt.replace("<CONTEXT_HISTORY>", meta_prompt)

    # add <TEMPORAL_HISTORY> to the prompt
    # get the last 10 messages 
    query = {"chat_id": chat_id}
    recent_messages = llm_chathistory.find(query).sort("timestamp", pymongo.DESCENDING).limit(10)
    # add the messages to the prompt
    meta_prompt = ""
    for message in recent_messages:
        meta_prompt += message["role"] + ": " + message["content"] + "\n"

    if meta_prompt == "":
        meta_prompt = "No recent messages found.\n"

    # add the meta prompt to the prompt
    prompt = prompt.replace("<TEMPORAL_HISTORY>", meta_prompt)

    messages = [{"role": "system", "content": prompt}, {"role": "user", "content": completion}]
    
    # close the connection
    mongodb_conn.close()

    return prompt, messages

