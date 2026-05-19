# Python 的 import 类似 Java 的 import，但导入的是模块、类或函数。
import os
from openai import OpenAI
from dotenv import load_dotenv
from typing import List, Dict

# load_dotenv() 会自动查找并加载 .env 文件。
# 加载后，可以用 os.getenv("变量名") 读取里面的配置。
load_dotenv()


class HelloAgentsLLM:
    # class 定义类，语法上不需要像 Java 一样写 public/private。
    # Python 用缩进表示代码块，类里面的函数就是方法。
    """
    为本书 "Hello Agents" 定制的LLM客户端。
    它用于调用任何兼容OpenAI接口的服务，并默认使用流式响应。
    """

    def __init__(self, model: str = None, apiKey: str = None, baseUrl: str = None, timeout: int = None):
        # __init__ 是构造方法，类似 Java 构造器。
        # self 类似 Java 里的 this，但 Python 要显式写在实例方法的第一个参数位置。
        # model: str 是类型注解，方便 IDE 和类型检查；运行时不会强制检查类型。
        # model=None 表示参数有默认值，不传时就是 None。
        """
        初始化客户端。优先使用传入参数，如果未提供，则从环境变量加载。
        """
        # a or b 是 Python 常见写法：如果 a 有值就用 a，否则用 b。
        # 这里表示：优先使用调用方传入的参数，否则从 .env/环境变量读取。
        self.model = model or os.getenv("LLM_MODEL_ID")
        apiKey = apiKey or os.getenv("LLM_API_KEY")
        baseUrl = baseUrl or os.getenv("LLM_BASE_URL")
        timeout = timeout or int(os.getenv("LLM_TIMEOUT", 60))

        # all([...]) 会检查列表里的每一项是否都为“真值”。
        # not all(...) 表示只要有一个缺失，就进入 if。
        if not all([self.model, apiKey, baseUrl]):
            # raise 类似 Java 里的 throw，用于抛出异常。
            raise ValueError("模型ID、API密钥和服务地址必须被提供或在.env文件中定义。")

        # self.client 是实例属性，类似 Java 里的 this.client。
        # OpenAI(...) 里的 api_key=... 是关键字参数，类似按参数名传参。
        self.client = OpenAI(api_key=apiKey, base_url=baseUrl, timeout=timeout)

    def think(self, messages: List[Dict[str, str]], temperature: float = 0) -> str:
        # messages: List[Dict[str, str]] 表示参数期望是“字典列表”。
        # 对应 Java 可以理解成 List<Map<String, String>>。
        # -> str 表示方法期望返回字符串；这也是类型注解，不是强制约束。
        """
        调用大语言模型进行思考，并返回其响应。
        """
        # f"..." 是格式化字符串，类似 Java 里的字符串模板/拼接。
        # {self.model} 会被替换成实例属性 self.model 的值。
        print(f"🧠 正在调用 {self.model} 模型...")
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                stream=True,
            )

            # 处理流式响应
            print("✅ 大语言模型响应成功:")
            collected_content = []
            # for ... in ... 类似 Java 的增强 for 循环。
            for chunk in response:
                # x or "" 表示如果 x 是 None 或空值，就用空字符串兜底。
                content = chunk.choices[0].delta.content or ""
                # end="" 表示 print 后不自动换行；flush=True 表示立即输出。
                print(content, end="", flush=True)
                # list.append(...) 类似 Java 里 List.add(...)。
                collected_content.append(content)
            print()  # 在流式输出结束后换行
            # "".join(list) 是 Python 拼接字符串列表的常用写法。
            return "".join(collected_content)

        except Exception as e:
            # except Exception as e 类似 Java 的 catch (Exception e)。
            print(f"❌ 调用LLM API时发生错误: {e}")
            return None


# --- 客户端使用示例 ---
if __name__ == '__main__':
    # 只有直接运行本文件时，下面代码才会执行。
    # 如果这个文件被 import 到别的文件中，这段示例代码不会自动执行。
    try:
        llmClient = HelloAgentsLLM()

        # Python 的列表用 []，字典用 {}。
        # 这里是一个 list，里面每个元素都是 dict。
        exampleMessages = [
            {"role": "system", "content": "You are a helpful assistant that writes Python code."},
            {"role": "user", "content": "写一个快速排序算法"}
        ]

        print("--- 调用LLM ---")
        responseText = llmClient.think(exampleMessages)
        # if responseText 表示 responseText 不是 None、不是空字符串时才进入。
        if responseText:
            print("\n\n--- 完整模型响应 ---")
            print(responseText)

    except ValueError as e:
        print(e)

