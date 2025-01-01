import autogen
from autogen.agentchat.agent import Agent
from autogen.agentchat.user_proxy_agent import UserProxyAgent
from autogen.agentchat.assistant_agent import AssistantAgent
import json
from jsonschema import validate
from copy import deepcopy

from schemas import initial_schema, interior_architect_schema, interior_designer_schema, engineer_schema

config_list_gpt4_prev = autogen.config_list_from_json(
    "OAI_CONFIG_LIST.json",
    filter_dict={
        "model": ["gpt-4-1106-preview"],
    },
)

# Set the API key from the first config
import os
with open("OAI_CONFIG_LIST.json", "r") as f:
    config_list = json.load(f)
    os.environ["OPENAI_API_KEY"] = config_list[0]["api_key"]

# OAI_CONFIG_LIST.json is needed! Check the Autogen repo for more info!
config_list_gpt4 = autogen.config_list_from_json(
    "OAI_CONFIG_LIST.json",
    filter_dict={
        "model": ["gpt-4"],
    },
)

config_list_gpt4o = autogen.config_list_from_json(
    "OAI_CONFIG_LIST.json",
    filter_dict = {
        "model": ["gpt-4o-mini"],
    }
)

gpt4_prev_config = {
    "cache_seed": 42,
    "temperature": 0.7,
    "top_p" : 1.0,
    "config_list": config_list_gpt4_prev,
    "timeout": 600,
}

gpt4_config = {
    "cache_seed": 42,
    "temperature": 0.7,
    "top_p" : 1.0,
    "config_list": config_list_gpt4o,
    "timeout": 600,
}

gpt4o_config = {
    "cache_seed": 42,
    "temperature": 0.7,
    "top_p" : 1.0,
    "config_list": config_list_gpt4o,
    "timeout": 600,
}

gpt4_json_config = deepcopy(gpt4o_config)
gpt4_json_config["temperature"] = 0.7
gpt4_json_config["config_list"][0]["response_format"] = { "type": "json_object" }

gpt4_json_engineer_config = deepcopy(gpt4o_config)
gpt4_json_engineer_config["temperature"] = 0.0
gpt4_json_engineer_config["config_list"][0]["response_format"] = { "type": "json_object" }

def is_termination_msg(content) -> bool:
    have_content = content.get("content", None) is not None
    if have_content and content["name"] == "Json_schema_debugger" and "SUCCESS" in content["content"]:
        return True
    return False


class JSONSchemaAgent(UserProxyAgent):
    def __init__(self, name : str, is_termination_msg):
        super().__init__(name, is_termination_msg=is_termination_msg, code_execution_config={"use_docker": False})

    def get_human_input(self, prompt: str) -> str:
        message = self.last_message()
        preps_layout = ['in front', 'on', 'in the corner', 'in the middle of']
        preps_objs = ['on', 'left of', 'right of', 'in front', 'behind', 'under', 'above']

        try:
            json_obj_new = json.loads(message["content"])
        except json.JSONDecodeError:
            return "Invalid JSON format. Please check your JSON syntax."

        try:
            json_obj_new_ids = [item["new_object_id"] for item in json_obj_new["objects_in_room"]]
        except KeyError:
            return "Use 'new_object_id' instead of 'object_id'!"
        except TypeError:
            return "Invalid objects_in_room format. Must be an array of objects."

        is_success = False
        try:
            validate(instance=json_obj_new, schema=initial_schema)
            is_success = True
        except Exception as e:
            feedback = str(e.message)
            
            if e.validator == "minItems":
                if "room_layout_elements" in str(e.absolute_path):
                    feedback = "Every object must have at least one room layout relationship (e.g. on south_wall, in the middle of room)"
            
            elif e.validator == "uniqueItems":
                if "objects_in_room" in str(e.absolute_path):
                    feedback = "Duplicate object IDs found. Each object must have a unique ID."

            elif e.validator == "required":
                if "room_layout_elements" in str(e.absolute_path):
                    feedback = "Missing required room layout relationships. Every object must specify its position relative to the room."
                elif "is_adjacent" in str(e.absolute_path):
                    feedback = "Missing is_adjacent field. Must specify whether objects are physically touching/close or not."

        if is_success:
            return "SUCCESS"
        return feedback

def create_agents(no_of_objects : int):
    user_proxy = autogen.UserProxyAgent(
        name="Admin",
        system_message = "A human admin.",
        is_termination_msg = is_termination_msg,
        code_execution_config={"use_docker": False}
    )

    json_schema_debugger = JSONSchemaAgent(
        name = "Json_schema_debugger",
        is_termination_msg = is_termination_msg,
    )
    interior_designer = autogen.AssistantAgent(
        name = "Interior_designer",
        llm_config = gpt4_json_config,
        human_input_mode = "NEVER",
        is_termination_msg = is_termination_msg,
        system_message = f""" Interior Designer. Suggest {no_of_objects} essential new objects to be added to the room based on the user preference, general functionality of the room and the room size.
        The suggested objects should contain the following information:

        1. Object name (ex. bed, desk, chair, monitor, bookshelf, etc.)
        2. Architecture style (ex. modern, classic, etc.)
        3. Material (ex. wood, metal, etc.)
        4. Bounding box size in meters (ex. Length : 1.0m, Width : 1.0m, Height : 1.0m). Only use "Length", "Width", "Height" as keys for the size of the bounding box!
        5. Quantity (ex. 1, 2, 3, etc.)

        IMPORTANT: Do not suggest any objects related to doors or windows, such as curtains, blinds, etc.

        Follow the JSON schema below:
        {interior_designer_schema}

        """
    )


    interior_architect = autogen.AssistantAgent(
        name = "Interior_architect",
        llm_config = gpt4_json_config,
        human_input_mode = "NEVER",
        is_termination_msg = is_termination_msg,
        system_message = f""" Interior Architect. Your role is to analyze the user preference, think about where the optimal
        placement for each object would be that the Interior Designer suggests and find a place for this object in the room and give a detailed description of it.

        For objects with quantity > 1, you MUST handle each instance separately and give them unique IDs. For example:
        If the Interior Designer suggests "2 chairs", you must:
        1. Create unique IDs: chair_1 and chair_2
        2. Place each chair separately with its own placement, proximity, and facing information
        3. Make sure each instance has a distinct and logical placement (e.g., don't put both chairs in the exact same spot)
        4. Reference the specific ID when describing relationships (e.g., "chair_1 is left of desk_1, chair_2 is right of desk_1")

        Give explicit answers for EACH object instance on these aspects:

        Placement: 
        Find a relative place for the object (ex. in the middle of the room, in the north-west corner, on the east wall, right of the desk, on the bookshelf...).
        For relative placement with other objects in the room use ONLY these exact prepositions: "on", "left of", "right of", "in front", "behind", "under", "above".
        For relative placement with the room layout elements (walls, the middle of the room, ceiling) use ONLY these exact prepositions: "on", "in the corner".
        You are not allowed to use any prepositions different from the ones above!! No "near", "next to", "in front of", etc.

        Proximity : 
        Proximity of this object to the relative placement objects:
        1. Adjacent : The object is physically contacting the other object or it is supported by the other object or they are touching or they are close to each other.
        2. Not Adjacent: The object is not physically contacting the other object and it is distant from the other object.

        Facing :
        Think about which wall (west/east/north/south_wall) this object should be facing and explicitly state this for each instance.

        IMPORTANT: 
        1. When referring to the middle of the room, always use "middle of the room" and never "middle of the floor"!
        2. Never use "near" or similar words - instead use precise prepositions like "left of", "right of", etc.
        3. Use "in front" instead of "in front of"
        4. For multiple instances of the same object type, always give each instance a unique ID and placement

        You must follow the following JSON schema:
        {interior_architect_schema}
        """
    )

    engineer = autogen.AssistantAgent(
        name = "Engineer",
        llm_config = gpt4_json_engineer_config,
        human_input_mode = "NEVER",
        is_termination_msg = is_termination_msg,
        system_message = f""" Engineer. You listen to the input by the Admin and create a JSON file.
        The Admin will provide:
        1. A list of room layout elements
        2. A list of existing objects in the room (can be empty)
        3. A new object to be placed, with its placement information

        Your job is to create a JSON object that combines the designer's object details with the architect's placement details.
        The object IDs have already been expanded (e.g. "armchair_1", "armchair_2"), so use these exact IDs.
        
        CRITICAL REQUIREMENTS:
        1. EVERY object MUST have at least one room_layout_element in its placement. This defines where the object is in relation to the room (walls, middle, corners).
        2. If an object is placed relative to another object (in objects_in_room), it still MUST specify its room position in room_layout_elements.
        3. Never leave room_layout_elements as an empty array - always specify at least one room layout relationship.
        4. Use EXACTLY the object IDs provided in the input - do not modify them.
        5. The "placement" field must include both room_layout_elements and objects_in_room based on the architect's placement description.
        6. All object IDs must be lowercase and end with a number (e.g. chair_1, table_2).
        7. When an object is placed relative to another object, you must specify whether they are adjacent using is_adjacent:
           - Adjacent: Objects are physically touching or very close (e.g. "chair_1 is on desk_1", "plant_1 is right of desk_1")
           - Not Adjacent: Objects are not touching and have space between them

        Use only the following JSON Schema to save the JSON object:
        {engineer_schema}
        """
    )

    return user_proxy, json_schema_debugger, interior_designer, interior_architect, engineer
