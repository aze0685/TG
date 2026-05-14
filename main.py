import os
import asyncio
import fal_client
from telegram.ext import Application, MessageHandler, filters
from openai import OpenAI

# 初始化 GPT (你的 GPT Key 就是用在这里当大脑的)
gpt_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def handle_message(update, context):
    # 1. 接收图片
    if update.message.photo:
        file = await update.message.photo[-1].get_file()
        context.user_data['last_img'] = file.file_path
        await update.message.reply_text("📸 原图已就绪。告诉我你想怎么改？（例如：去掉墨镜，头发换成七彩）")
        return

    # 2. 接收指令并处理
    if update.message.text and 'last_img' in context.user_data:
        user_input = update.message.text
        status = await update.message.reply_text("🧠 GPT 正在分析修改区域并调用云端算力...")

        try:
            # 步骤 A：利用 GPT 生成精准的英文修改指令
            gpt_res = gpt_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a professional image editor. Transform user requests into precise technical editing instructions. Focus only on the changes, and emphasize 'KEEP THE FACE FEATURES UNCHANGED'. "},
                    {"role": "user", "content": f"User Request: {user_input}"}
                ]
            )
            refined_prompt = gpt_res.choices[0].message.content

            # 步骤 B：调用 fal.ai 专门的编辑模型 (这才是真正的“原图修改”)
            handler = await asyncio.to_thread(
                fal_client.subscribe,
                "fal-ai/flux-pro/v1/editing", 
                arguments={
                    "image_url": context.user_data['last_img'],
                    "edit_instruction": refined_prompt,
                    "prompt": f"highly detailed, professional retouching, {refined_prompt}, maintain original identity and background.",
                    "guidance_scale": 7.5
                }
            )
            
            await update.message.reply_photo(handler['images'][0]['url'], caption="✨ 利用 GPT + fal.ai 精准修改完成！")
            
        except Exception as e:
            await update.message.reply_text(f"⚠️ 运行出错: {str(e)}")
        finally:
            await status.delete()

if __name__ == '__main__':
    app = Application.builder().token(os.getenv("TELEGRAM_TOKEN")).build()
    app.add_handler(MessageHandler(filters.ALL, handle_message))
    app.run_polling()
