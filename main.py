from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import re
import os
import requests
from dotenv import load_dotenv
from supabase import create_client, Client

# 加载环境变量
load_dotenv()

# 创建FastAPI应用 - 确保在文件最顶层定义
app = FastAPI()

# 根路径测试接口
@app.get("/")
def read_root():
    return {"status": "Vercel is Alive!"}

# 获取环境变量的辅助函数
def get_env_variable(name):
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value

@app.post('/api/process')
async def process_text(request: Request):
    try:
        # 获取请求数据
        data = await request.json()
        text = data.get('text')
        
        if not text:
            raise HTTPException(status_code=400, detail='文本不能为空')
        
        # 调用大模型API处理文本
        result = process_with_ai(text)
        
        # 写入Supabase数据库
        try:
            # 惰性加载Supabase客户端
            supabase = create_client(
                get_env_variable('SUPABASE_URL'),
                get_env_variable('SUPABASE_KEY')
            )
            
            supabase.table('contents').insert({
                'original_text': text,
                'category': result['category'],
                'summary': result['context_summary'],
                'markdown': result['markdown']
            }).execute()
            print("数据写入成功")
        except Exception as db_error:
            print(f"数据库写入失败: {db_error}")
            # 数据库写入失败不影响返回结果
        
        return JSONResponse(content=result)
    except HTTPException:
        raise
    except Exception as e:
        print(f"处理失败: {e}")
        raise HTTPException(status_code=500, detail='处理失败')

@app.get('/api/history')
async def get_history():
    try:
        # 惰性加载Supabase客户端
        supabase = create_client(
            get_env_variable('SUPABASE_URL'),
            get_env_variable('SUPABASE_KEY')
        )
        
        # 从Supabase数据库获取历史记录
        response = supabase.table('contents').select('*').execute()
        return JSONResponse(content=response.data)
    except Exception as e:
        print(f"获取历史记录失败: {e}")
        return JSONResponse(content=[])

def process_with_ai(text):
    try:
        # 构建系统提示
        system_prompt = """你是一个专业的文本处理助手，为服装设计师/产品经理提供服务。请对输入的文本进行以下处理：
1. 分类：根据内容，自动为这段文本打上1-2个分类标签（如：设计灵感、技术学习、生活碎片等）。
2. 总结：用一两句话，极其精准地总结这段内容对服装设计师/产品经理有什么潜在价值或上下文关联。
3. Markdown：生成符合Markmap的层级Markdown文本，清晰展示内容结构，不要用代码块包裹。

请以JSON格式返回结果，包含以下字段：
- category: 分类标签（数组形式）
- context_summary: 上下文总结
- markdown: Markmap格式的Markdown文本"""
        
        # 获取API密钥
        api_key = get_env_variable('API_KEY')
        
        # 调用大模型API
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        data = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请处理以下文本：\n{text}"}
            ],
            "temperature": 0.7
        }
        
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        
        # 解析返回结果
        response_data = response.json()
        result_text = response_data['choices'][0]['message']['content']
        
        # 提取JSON部分
        json_match = re.search(r'\{[^\}]*\}', result_text)
        if json_match:
            import json
            return json.loads(json_match.group())
        else:
            # 如果返回的不是JSON，手动构建结果
            return {
                "category": ["未分类"],
                "context_summary": "无法生成总结",
                "markdown": f"# 内容\n\n{text}"
            }
    except Exception as e:
        print(f"AI处理失败: {e}")
        # 失败时返回默认结果
        return {
            "category": ["未分类"],
            "context_summary": "无法生成总结",
            "markdown": f"# 内容\n\n{text}"
        }
