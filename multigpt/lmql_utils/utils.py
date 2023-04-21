import asyncio
import time

from openai.error import RateLimitError
from autogpt import token_counter
from autogpt.chat import cfg, generate_context, create_chat_message
from autogpt.logs import logger
from multigpt.lmql_utils import _queries


def lmql_chat_with_ai(
        prompt, user_input, full_message_history, permanent_memory, token_limit
):
    """Interact with the OpenAI API, sending the prompt, user input, message history,
    and permanent memory."""
    while True:
        try:
            """
            Interact with the OpenAI API, sending the prompt, user input,
                message history, and permanent memory.

            Args:
                prompt (str): The prompt explaining the rules to the AI.
                user_input (str): The input from the user.
                full_message_history (list): The list of all messages sent between the
                    user and the AI.
                permanent_memory (Obj): The memory object containing the permanent
                  memory.
                token_limit (int): The maximum number of tokens allowed in the API call.

            Returns:
            str: The AI's response.
            """
            model = cfg.fast_llm_model  # TODO: Change model from hardcode to argument
            # Reserve 1000 tokens for the response

            logger.debug(f"Token limit: {token_limit}")
            send_token_limit = token_limit - 1000

            relevant_memory = (
                ""
                if len(full_message_history) == 0
                else permanent_memory.get_relevant(str(full_message_history[-9:]), 10)
            )

            logger.debug(f"Memory Stats: {permanent_memory.get_stats()}")

            (
                next_message_to_add_index,
                current_tokens_used,
                insertion_index,
                current_context,
            ) = generate_context(prompt, relevant_memory, full_message_history, model)

            while current_tokens_used > 2500:
                # remove memories until we are under 2500 tokens
                relevant_memory = relevant_memory[:-1]
                (
                    next_message_to_add_index,
                    current_tokens_used,
                    insertion_index,
                    current_context,
                ) = generate_context(
                    prompt, relevant_memory, full_message_history, model
                )

            current_tokens_used += token_counter.count_message_tokens(
                [create_chat_message("user", user_input)], model
            )  # Account for user input (appended later)

            while next_message_to_add_index >= 0:
                # print (f"CURRENT TOKENS USED: {current_tokens_used}")
                message_to_add = full_message_history[next_message_to_add_index]

                tokens_to_add = token_counter.count_message_tokens(
                    [message_to_add], model
                )
                if current_tokens_used + tokens_to_add > send_token_limit:
                    break

                # Add the most recent message to the start of the current context,
                #  after the two system prompts.
                current_context.insert(
                    insertion_index, full_message_history[next_message_to_add_index]
                )

                # Count the currently used tokens
                current_tokens_used += tokens_to_add

                # Move to the next most recent message in the full message history
                next_message_to_add_index -= 1

            # Append user input, the length of this is accounted for above
            current_context.extend([create_chat_message("user", user_input)])

            # Calculate remaining tokens
            tokens_remaining = token_limit - current_tokens_used
            # assert tokens_remaining >= 0, "Tokens remaining is negative.
            # This should never happen, please submit a bug report at
            #  https://www.github.com/Torantulino/Auto-GPT"

            # Debug print the current context
            logger.debug(f"Token limit: {token_limit}")
            logger.debug(f"Send Token Count: {current_tokens_used}")
            logger.debug(f"Tokens remaining for response: {tokens_remaining}")
            logger.debug("------------ CONTEXT SENT TO AI ---------------")
            for message in current_context:
                # Skip printing the prompt
                if message["role"] == "system" and message["content"] == prompt:
                    continue
                logger.debug(f"{message['role'].capitalize()}: {message['content']}")
                logger.debug("")
            logger.debug("----------- END OF CONTEXT ----------------")

            # TODO: use a model defined elsewhere, so that model can contain
            # temperature and other settings we care about
            assistant_reply = lmql_create_chat_completion(
                model=model,
                messages=current_context,
                max_tokens=tokens_remaining,
            )

            # Update full message history
            full_message_history.append(create_chat_message("user", user_input))
            full_message_history.append(
                create_chat_message("assistant", assistant_reply)
            )

            return assistant_reply
        except RateLimitError:
            # TODO: When we switch to langchain, this is built in
            print("Error: ", "API Rate Limit Reached. Waiting 10 seconds...")
            time.sleep(10)


def lmql_create_chat_completion(model="gpt-3.5-turbo", messages=None, max_tokens=0):
    async def _query_chat_completion():
        if model == "gpt-4":
            return (await _queries.create_chat_completion_gpt4(messages))[0].prompt
        else:
            return (await _queries.create_chat_completion_gpt3(messages))[0].prompt

    loop = asyncio.get_event_loop()
    chat_completion = loop.run_until_complete(_query_chat_completion())
    return _extract_response(chat_completion, '{')


def lmql_get_emotional_state(message):
    async def _query_emotional_state():
        result = (await _queries.classify_emotion(message))
        #TODO perhaps add offset to neutral emotion? Most of the messages are too polite to be considered anything but 'neutral'
        return result.variables['CLASSIFICATION']

    loop = asyncio.get_event_loop()
    emotion = loop.run_until_complete(_query_emotional_state())
    return emotion


# internal helper functions


def _extract_response(input_string, first_char):
    substring = "<lmql:user/>"
    last_occurrence_index = input_string.rfind(substring)

    if last_occurrence_index != -1:
        input_string = input_string[last_occurrence_index + len(substring):]
        first_occurrence_index = input_string.find(first_char)
        if first_occurrence_index != -1:
            return input_string[first_occurrence_index:]
    return None
