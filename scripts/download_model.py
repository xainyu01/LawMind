from sentence_transformers import SentenceTransformer
import os
from dotenv import load_dotenv

load_dotenv()
model_name = os.getenv("EMBEDDING_MODEL_NAME", "BAAI/bge-small-zh")
print(f"正在下载模型: {model_name}")
model = SentenceTransformer(model_name, cache_folder="./models")
print(f"模型已下载到: ./models/{model_name}")
print("下载完成!")
