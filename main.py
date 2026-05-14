import os
import asyncio
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import fal_client
from openai import OpenAI

# 设置日志
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# 初始化 API 客户端
client_gpt = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 简单的内存存储，用于处理多图逻辑
user_sessions = {}

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    # --- 处理图片上传 ---
    if update.message.photo:
        file = await update.message.photo[-1].get_file()
        if chat_id not in user_sessions:
            user_sessions[chat_id] = []
        user_sessions[chat_id].append(file.file_path)
        
        count = len(user_sessions[chat_id])
        await update.message.reply_text(f"✅ 已接收第 {count} 张图片。请继续发送图片或直接输入 P 图指令。")
        return

    # --- 处理文字指令 (P图逻辑) ---
    if update.message.text:
        user_instr = update.message.text
        if chat_id not in user_sessions or not user_sessions[chat_id]:
            await update.message.reply_text("❌ 请先发送至少一张图片。")
            return

        status_msg = await update.message.reply_text("🧠 正在理解您的意图并调动云端 GPU...")

        try:
            images = user_sessions[chat_id]
            
            # 1. 让 GPT 充当“万能路由”，生成专业 Prompt 和任务参数
            # 它会根据图片数量和指令，自动判断是“扩图”、“擦除”还是“融合”
            gpt_response = client_gpt.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "你是一个全能修图专家。根据用户指令和图片数量，生成一段详细的英文提示词(prompt)。如果用户提供了两张图，通常是将第一张图的元素无痕融合到第二张图中。请直接输出最终的英文提示词。"},
                    {"role": "user", "content": f"用户指令: {user_instr}, 图片数量: {len(images)}"}
                ]
            )
            final_prompt = gpt_response.choices[0].message.content

            # 2. 调用 Fal.ai 的全能上下文接口 (30秒内出片)
            # 根据图片数量决定参考图
            args = {
                "prompt": final_prompt,
                "image_url": images[-1], # 最后一张作为底图
                "sync_mode": False
            }
            if len(images) > 1:
                args["reference_image_url"] = images[0] # 第一张作为参考元素

            # 执行 P 图
            handler = await asyncio.to_thread(
                fal_client.subscribe,
                "fal-ai/flux-pro/v1/context", 
                arguments=args
            )
            
            # 3. 发送结果并清空缓存
            await update.message.reply_photo(handler['images'][0]['url'], caption="✨ P 图完成！")
            user_sessions[chat_id] = [] 

        except Exception as e:
            await update.message.reply_text(f"⚠️ 出错啦: {str(e)}")
        finally:
            await status_msg.delete()

if __name__ == '__main__':
    # 从 Railway 环境变量获取 Token
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        print("错误: 找不到 TELEGRAM_TOKEN 环境变量")
    else:
        app = Application.builder().token(token).build()
        app.add_handler(MessageHandler(filters.ALL, handle_message))
        print("🚀 机器人已在 Railway 启动...")
        app.run_polling()
