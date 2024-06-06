from abc import ABC, abstractmethod
import logging
from pathlib import Path
import sys
from typing import Any
import pandas as pd
from src.conversation.conversation_log import conversation_log
from src.conversation.context import context
from src.config_loader import ConfigLoader
from src.llm.sentence import sentence
from src.games.external_character_info import external_character_info
import src.utils as utils

class gameable(ABC):
    """Abstract class for different implementations of games to support. 
    Make a subclass for every game that Mantella is supposed to support and implement this interface
    Anything that is specific to a certain game should end up in one of these subclasses.
    If there are new areas where a game specific handling is required, add new methods to this and implement them in all of the subclasses

    Args:
        ABC (_type_): _description_
    """
    def __init__(self, path_to_character_df: str, mantella_game_folder_path: str):
        try:
            self.__character_df: pd.DataFrame = self.__get_character_df(path_to_character_df)
        except:
            logging.error(f'Unable to read / open {path_to_character_df}. If you have recently edited this file, please try reverting to a previous version. This error is normally due to using special characters, or saving the CSV in an incompatible format.')
            input("Press Enter to exit.")

        # if the exe is being run by another process, store conversation data in MantellaData rather than the local data folder
        if "--integrated" in sys.argv:
            self.__conversation_folder_path = str(Path(utils.resolve_path()).parent.parent.parent.parent)+'/MantellaData/conversations'
        else:
            self.__conversation_folder_path = f"data/{mantella_game_folder_path}/conversations"
        
        conversation_log.game_path = self.__conversation_folder_path
    
    @property
    def character_df(self) -> pd.DataFrame:
        return self.__character_df
    
    @property
    def conversation_folder_path(self) -> str:
        return self.__conversation_folder_path
    
    def __get_character_df(self, file_name: str) -> pd.DataFrame:
        encoding = utils.get_file_encoding(file_name)
        character_df = pd.read_csv(file_name, engine='python', encoding=encoding)
        character_df = character_df.loc[character_df['voice_model'].notna()]

        return character_df
    
    @abstractmethod
    def load_external_character_info(self, id: str, name: str, race: str, gender: int, actor_voice_model_name: str)-> external_character_info:
        """This loads extra information about a character that can not be gained from the game. i.e. bios or voice_model_names for TTS

        Args:
            id (str): the id of the character to get the extra information from
            name (str): the name of the character to get the extra information from
            race (str): the race of the character to get the extra information from
            gender (int): the gender of the character to get the extra information from
            actor_voice_model_name (str): the ingame voice model name of the character to get the extra information from

        Returns:
            external_character_info: the missing information
        """
        pass    

    @abstractmethod
    def prepare_sentence_for_game(self, queue_output: sentence, context_of_conversation: context, config: ConfigLoader):
        """Does what ever is needed to play a sentence ingame

        Args:
            queue_output (sentence): the sentence to play
            context_of_conversation (context): the context of the conversation
            config (ConfigLoader): the current config
        """
        pass

    @abstractmethod
    def is_sentence_allowed(self, text: str, count_sentence_in_text: int) -> bool:
        """Checks a sentence generated by the LLM for game specific stuff

        Args:
            text (str): the sentence text to check
            count_sentence_in_text (int): count of sentence in text

        Returns:
            bool: True if sentence is allowed, False otherwise
        """
        pass

    @abstractmethod
    def load_unnamed_npc(self, name: str, race: str, gender: int, ingame_voice_model:str) -> dict[str, Any]:
        """Loads a generic NPC if the NPC is not found in the CSV file

         Args:
            name (str): the name of the character
            race (str): the race of the character
            gender (int): the gender of the character
            ingame_voice_model (str): the ingame voice model name of the character

        Returns:
            dict[str, Any]: A dictionary containing NPC info (name, bio, voice_model, advanced_voice_model, voice_folder)
        """
        pass

    def find_character_info(self, character_id: str, character_name: str, race: str, gender: int, ingame_voice_model: str):
        # TODO: try loading the NPC's voice model as soon as the NPC is found to speed up run time and so that potential errors are raised ASAP
        full_id_len = 6
        full_id_search = character_id[-full_id_len:].lstrip('0')  # Strip leading zeros from the last 6 characters

        # Function to remove leading zeros from hexadecimal ID strings
        def remove_leading_zeros(hex_str):
            if pd.isna(hex_str):
                return ''
            return str(hex_str).lstrip('0')

        id_match = self.character_df['base_id'].apply(remove_leading_zeros).str.lower() == full_id_search.lower()
        name_match = self.character_df['name'].astype(str).str.lower() == character_name.lower()

        character_race = race.split('<')[1].split('Race ')[0] # TODO: check if this covers "character_currentrace.split('<')[1].split('Race ')[0]" from FO4
        race_match = self.character_df['race'].astype(str).str.lower() == character_race.lower()

        # Partial ID match with decreasing lengths
        partial_id_match = pd.Series(False, index=self.character_df.index)
        for length in [5, 4, 3]:
            if partial_id_match.any():
                break
            partial_id_search = character_id[-length:].lstrip('0')  # strip leading zeros from partial ID search
            partial_id_match = self.character_df['base_id'].apply(
                lambda x: remove_leading_zeros(str(x)[-length:]) if pd.notna(x) and len(str(x)) >= length else remove_leading_zeros(str(x))
            ).str.lower() == partial_id_search.lower()

        is_generic_npc = False
        try: # match name, full ID, race (needed for Fallout 4 NPCs like Curie)
            logging.info(" # match name, full ID, race (needed for Fallout 4 NPCs like Curie)")
            character_info = self.character_df.loc[name_match & id_match & race_match].to_dict('records')[0]
        except IndexError:
            try: # match name and full ID
                logging.info(" # match name and full ID")
                character_info = self.character_df.loc[name_match & id_match].to_dict('records')[0]
            except IndexError:
                try: # match name, partial ID, and race
                        logging.info(" # match name, partial ID, and race")
                        character_info = self.character_df.loc[name_match & partial_id_match & race_match].to_dict('records')[0]
                except IndexError:
                    try: # match name and partial ID
                        logging.info(" # match name and partial ID")
                        character_info = self.character_df.loc[name_match & partial_id_match].to_dict('records')[0]
                    except IndexError:
                        try: # match name and race
                            logging.info(" # match name and race")
                            character_info = self.character_df.loc[name_match & race_match].to_dict('records')[0]
                        except IndexError:
                            try: # match just name
                                logging.info(" # match just name")
                                character_info = self.character_df.loc[name_match].to_dict('records')[0]
                            except IndexError:
                                try: # match just ID
                                    logging.info(" # match just ID")
                                    character_info = self.character_df.loc[id_match].to_dict('records')[0]
                                except IndexError: # treat as generic NPC
                                    logging.info(f"Could not find {character_name} in skyrim_characters.csv. Loading as a generic NPC.")
                                    character_info = self.load_unnamed_npc(character_name, character_race, gender, ingame_voice_model)
                                    is_generic_npc = True

        return character_info, is_generic_npc