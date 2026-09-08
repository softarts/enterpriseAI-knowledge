"""
qa_service — 单次检索 + 单次生成的 RAG 问答层。

模块结构：
    models.py        内部数据类（RetrievedChunk / ReflectionResult / AnswerResult）
    config.py        配置（TOP_K、置信度阈值、LLM 环境变量）
    retrieval.py     embedding 编码 + ChromaDB 检索 + 置信度判断
    prompt_builder.py context 拼接 + system prompt 常量
    llm_client.py    LangChain ChatOpenAI LCEL chain 封装
    reflection.py    Reflection 接口 + 占位实现（下阶段替换函数体）
    pipeline.py      主入口 answer_question()
"""
