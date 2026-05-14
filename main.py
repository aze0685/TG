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

# 简单的内存存储
user_sessions = {}

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    # --- 1. 处理图片接收 ---
    if update.message.photo:
        file = await update.message.photo[-1].get_file()
        if chat_id not in user_sessions:
            user_sessions[chat_id] = []
        user_sessions[chat_id].append(file.file_path)
        
        count = len(user_sessions[chat_id])
        await update.message.reply_text(f"📸 已收到第 {count} 张图。如果是多图处理请继续发，否则请直接输入指令（如：换成红头发）。")
        return

    # --- 2. 处理文字指令 ---
    if update.message.text:
        user_instr = update.message.text
        if chat_id not in user_sessions or not user_sessions[chat_id]:
            await update.message.reply_text("❌ 请先发送图片给我。")
            return

        status_msg = await update.message.reply_text("🚀 正在调用云端 GPU 进行无痕处理...")

        try:
            images = user_sessions[chat_id]
            
            # 让 GPT 生成专业的英文提示词
            gpt_response = client_gpt.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "你是一个AI图像大师。将用户的中文修改要求转化为详细的英文描述。如果是多图，请描述如何将第一张图的元素完美融合到最后一张图中。"},
                    {"role": "user", "content": f"要求: {user_instr}, 图片数: {len(images)}"}
                ]
            )
            final_prompt = gpt_response.choices[0].message.content

            # 修改点：使用官方标准接口路径
            # 如果是单图修改，使用 image_to_image 逻辑
            # 如果是多图融合，Fal.ai 建议使用具备参考图能力的模型
            model_path = "fal-ai/flux-pro/v1.1" 
            
            args = {
                "prompt": final_prompt,
                "image_url": images[-1],  # 最后一张图作为底图
            }
            
            # 如果有参考图（P图场景）
            # 注意：某些模型参数名不同，此处使用通用适配
            # 也可以尝试 "fal-ai/flux/dev/image-to-image"
            
            handler = await asyncio.to_thread(
                fal_client.subscribe,
                model_path,
                arguments=args
            )
            
            await update.message.reply_photo(handler['images'][0]['url'], caption="✨ 处理完成！")
            user_sessions[chat_id] = [] # 成功后清空

        except Exception as e:
            error_str = str(e)
            if "Exhausted balance" in error_str:
                await update.message.reply_text("💰 Fal.ai 余额不足了，请前往官网充值或联系管理员。")
            else:
                await update.message.reply_text(f"⚠️ 出现错误: {error_str}")
        finally:
            await status_msg.delete()

if __name__ == '__main__':
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        print("错误: 找不到 TELEGRAM_TOKEN")
    else:
        app = Application.builder().token(token).build()
        app.add_handler(MessageHandler(filters.ALL, handle_message))
        print("🚀 机器人已在 Railway 更新启动...")
        app.run_polling()
