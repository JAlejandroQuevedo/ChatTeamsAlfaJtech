from botbuilder.core import ActivityHandler, MessageFactory, TurnContext, StoreItem, MemoryStorage
from botbuilder.schema import ChannelAccount
from botbuilder.azure import CosmosDbPartitionedStorage, CosmosDbPartitionedConfig
from botbuilder.core.teams import TeamsActivityHandler, TeamsInfo
from botbuilder.schema import CardAction, HeroCard, Mention, ConversationParameters, Attachment, Activity, Entity
from botbuilder.schema.teams import TeamInfo, TeamsChannelAccount
from botbuilder.schema._connector_client_enums import ActionTypes
import asyncio
import requests
from openai import OpenAI
import os
from dotenv import load_dotenv
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from config import DefaultConfig


CONFIG = DefaultConfig()
load_dotenv()  # Carga las variables del archivo .env
openai_key = os.environ.get('OPENAI_API_KEY')
openaiclient = OpenAI()


service_endpoint = "https://alfa-ai-search.search.windows.net"
api_key = os.environ.get('API_KEY')
index_name = "alfa_bot"
endpoint = f"{service_endpoint}/indexes/{index_name}/docs/search?api-version=2021-04-30-Preview"
search_client = SearchClient(service_endpoint, index_name, AzureKeyCredential(api_key))

intro_contexto = "Nunca te disculpes al responder. Utiliza únicamente esta información de referencia para contestar las preguntas del usuario. Si respondes algo fuera de la información de referencia, menciona explícitamente 'Esta información no proviene directamente de Alfa'. Cada extracto es independiente del anterior y no tienen relación: "
instruccion = "Tu nombre es AlfaBot, y eres un Asistente virtual inteligente para el corporativo de la empresa Alfa. Responde únicamente en español. Si te dan las gracias, responde que es un gusto ayudar y si hay algo más en lo que puedas asistirlos. Utiliza el historial de la conversación como referencia. Utiliza solo la información de referencia brindada. Si tu respuesta incluye algo que no se encuentre en la información de referencia brindada, añade en negritas 'Esta información no proviene de los documentos internos de Alfa'. No respondas preguntas que no sean de Alfa y sus procesos. Nunca te disculpes por confusiones en la conversación. Si no conoces la respuesta menciona que no cuentas con esa información. Utiliza de manera preferente la información de referencia con más exactitud y apego a la pregunta. Responde de manera concisa y concreta. Respuestas breves y atinadas, busca hacer listados y presentar la información de una manera útil y accesible. Si te preguntan acerca de tu alcance, información que conoces, qué sabes hacer o tu base de conocimientos, responde que conoces las políticas generales de Alfa así como las matrices de control principales. Algunos ejemplos de la información que conoces son: políticas de viaje, procesos de recursos humanos, procesos comerciales, procesos de finanzas, entre muchos otros. Responde dando detalles y enriqueciendo la pregunta. Siempre que puedas haz listados para organizar tu respuesta, usando bullets, negritas, dando respuestas largas y estructuradas.•  Preguntar si la información proporcionada ha sido útil y si hay algo más en lo que pueda ayudar. Si la información solicitada no está disponible dirigirlo con el departamento de Tecnología de la Información o contacto que este como responsable de la carpeta del tema a preguntar. Si el usuario quiere revisar dudas y sugerencias puede contactarse con el área de Tecnología de la Información de Alfa: tecnologia@alfa.com.mx No responder con información pública ni preguntas que no estén relacionadas con la información correspondiente cargada. Amablemente que pueda informar al empleado que solo puede asistir con consultas relacionadas con la empresa"


class UtteranceLog(StoreItem):
    """
    Class for storing a log of utterances (text of messages) as a list.
    """
    def __init__(self):
        super(UtteranceLog, self).__init__()
        self.messages = []
        self.user_info = None  # Información del usuario
        self.turn_number = 0
        self.e_tag = "*"
        self.carpetas = []  # Lista de carpetas a las que tiene acceso el usuario

class alfabot(TeamsActivityHandler):

    def __init__(self):
        cosmos_config = CosmosDbPartitionedConfig(
            container_throughput=400,
            cosmos_db_endpoint=CONFIG.COSMOS_DB_URI,
            auth_key=CONFIG.COSMOS_DB_PRIMARY_KEY,
            database_id=CONFIG.COSMOS_DB_DATABASE_ID,
            container_id=CONFIG.COSMOS_DB_CONTAINER_ID,
            compatibility_mode = False
        )
        self.storage = CosmosDbPartitionedStorage(cosmos_config)

    async def on_members_added_activity(
        self, members_added: [ChannelAccount], turn_context: TurnContext
    ):
        for member in members_added:
            if member.id != turn_context.activity.recipient.id:
                await turn_context.send_activity("¡Hola, soy AlfaBot! ¿Cómo puedo ayudarte hoy?")

    async def on_message_activity(self, turn_context: TurnContext):
        user_message = turn_context.activity.text
        conversation_id = turn_context.activity.conversation.id

        #typing
        await turn_context.send_activity(Activity(type="typing"))

        # read the state object
        store_items = await self.storage.read([conversation_id])

        if conversation_id not in store_items:
            # add the utterance to a new state object.
            utterance_log = UtteranceLog()
            utterance_log.messages.append(user_message)
            utterance_log.turn_number = 1

            try:
                member_info = await asyncio.wait_for(
                    TeamsInfo.get_member(turn_context, turn_context.activity.from_property.id),
                    timeout=5  # Set your desired timeout value in seconds
                )
                if member_info:
                    utterance_log.user_info = member_info.email

            except Exception as e:
                # Envía un mensaje de error al usuario
                await turn_context.send_activity(
                    MessageFactory.text(f"{e}")
                )

        else:
            # add new message to list of messages existing state object.
            utterance_log: UtteranceLog = store_items[conversation_id]
            utterance_log.messages.append(user_message)
            utterance_log.turn_number = utterance_log.turn_number + 1
        
        try:
            # Save the user message to your Storage.
            changes = {conversation_id: utterance_log}
            await self.storage.write(changes)

            # Obtener los últimos 4 mensajes de la conversación
            last_4_messages = utterance_log.messages[-4:]

            # Obtener los últimos 8 mensajes de la conversación
            last_8_messages = utterance_log.messages[-8:]
            
            # Generar embedding de la pregunta
            query_embedding_largo = openaiclient.embeddings.create(model="text-embedding-3-large", input="\n".join(last_4_messages), dimensions=1024).data[0].embedding
            query_embedding_corto = openaiclient.embeddings.create(model="text-embedding-3-large", input=user_message, dimensions=1024).data[0].embedding
            
            # Crear consultas vectorizadas
            vector_query = VectorizedQuery(vector=query_embedding_corto, k_nearest_neighbors=7, fields="Embedding")
            vector_query_largo = VectorizedQuery(vector=query_embedding_largo, k_nearest_neighbors=7, fields="Embedding")

            # Realizar búsqueda en Azure Search
            results = search_client.search(  
                search_text=None,  
                vector_queries=[vector_query],
                select=["Chunk","Adicional","FileName"],
                filter="Folder eq '1727468181184x887443586264191900' or Folder eq '1721838331185x391888654169602750' or Folder eq '1721838293918x578567098933541200' or Folder eq '1721838273084x997249294344777400' or Folder eq '1724297146467x528248112589696500' or Folder eq '1724297132046x157473295543779870' or Folder eq '1724297122954x246675696308903400' or Folder eq '1724297114861x824556494556945700' or Folder eq '1724297105904x395803296537081500' or Folder eq '1724297093236x840642798817826400' or Folder eq '1721838331185x391888654169602750' or Folder eq '1727468160291x847487420923683800'"
            )

            results_largo = search_client.search(  
                search_text=None,  
                vector_queries=[vector_query_largo],
                select=["Chunk","Adicional","FileName"],
                filter="Folder eq '1727468181184x887443586264191900' or Folder eq '1721838331185x391888654169602750' or Folder eq '1721838293918x578567098933541200' or Folder eq '1721838273084x997249294344777400' or Folder eq '1724297146467x528248112589696500' or Folder eq '1724297132046x157473295543779870' or Folder eq '1724297122954x246675696308903400' or Folder eq '1724297114861x824556494556945700' or Folder eq '1724297105904x395803296537081500' or Folder eq '1724297093236x840642798817826400' or Folder eq '1721838331185x391888654169602750' or Folder eq '1727468160291x847487420923683800'"
            )
            
            # Iterar sobre los resultados y obtener los primeros 4 Chunks
            chunks = [
                f"INICIA UN NUEVO EXTRACTO.\n Nombre del documento:\n{result['FileName']}\nInstrucciones adicionales si se usa este extracto:\n{result['Adicional']}\nContenido del extracto:\n{result['Chunk']}\n TERMINA EXTRACTO\n"
                for i, result in enumerate(results) if i < 8
                ]
            chunks_concatenados = "\n".join(chunks)

            # Iterar sobre los resultados largos y obtener los primeros 4 Chunks
            chunks_largo = [
                f"INICIA UN NUEVO EXTRACTO.\n Nombre del documento:\n{result['FileName']}\nInstrucciones adicionales si se usa este extracto:\n{result['Adicional']}\nContenido del extracto:\n{result['Chunk']}\n TERMINA EXTRACTO\n"
                for i, result in enumerate(results_largo) if i < 8
            ]
            chunks_concatenados_largo = "\n".join(chunks_largo)

            
            # Generar la respuesta utilizando OpenAI
            response = openaiclient.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=4500,
                messages=[
                    {"role": "system", "content": intro_contexto + "\nHistorial de conversación: " + "\n".join(last_8_messages)},
                    {"role": "system", "content": chunks_concatenados},
                    {"role": "system", "content": chunks_concatenados_largo},
                    {"role": "user", "content": user_message},
                    {"role": "system", "content": instruccion}
                ]
            )

            if response.choices[0].message.role == 'assistant':
                bot_response = response.choices[0].message.content
                await turn_context.send_activity(MessageFactory.text(f"{bot_response}<br><br>*Los datos son informativos, es importante consultar la fuente de referencia.*"))
                
                # Almacenar la respuesta del bot
                utterance_log.messages.append(bot_response)
                changes = {conversation_id: utterance_log}
                await self.storage.write(changes)

                # Almacenar pregunta y respuesta del bot en Bubble.io
                bubble_data = {
                    "question": user_message,
                    "answer": bot_response,
                    "user_email": utterance_log.user_info
                }
                # Aquí añadirías el código para enviar `bubble_data` a tu API de Bubble.io
                import requests
                bubble_webhook_url = "https://alfa-48373.bubbleapps.io/api/1.1/wf/webhook"
                response = requests.post(bubble_webhook_url, json=bubble_data)

            else:
                # No se recibió una respuesta válida de OpenAI
                await turn_context.send_activity(
                    MessageFactory.text("No se pudo generar una respuesta del bot.")
                )

        except Exception as e:
            # Envía un mensaje de error al usuario
            await turn_context.send_activity(
                MessageFactory.text(f"{e}")
            )
