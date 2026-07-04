```
xxx-service
 ├── app
 │   ├── main.py           # 应用入口，初始化FastAPI/Flask/Django实例
 │   ├── config            # 配置层
 │   │                     # 存放：数据库配置、Redis配置、环境变量加载、跨域设置等
 │   ├── api               # 接口层（对应Controller）
 │   │                     # 接收请求，参数校验，调用service，不写业务逻辑
 │   │   └── v1            # 按版本划分接口
 │   ├── services          # 业务逻辑层（对应Service）
 │   │                     # 处理核心业务、事务管理、复杂逻辑判断
 │   ├── models            # 数据模型层（对应Entity/Mapper）
 │   │                     # ORM模型定义（SQLAlchemy/Peewee等），对应数据库表结构
 │   ├── schemas           # 数据校验与序列化层（对应DTO/VO）
 │   │                     # Pydantic模型或Marshmallow Schema，用于请求参数校验和响应数据格式化
 │   ├── repositories      # 数据访问层（可选，对应Mapper/DAO）
 │   │                     # 封装复杂的数据库查询操作，简单项目可合并至models或services
 │   ├── utils             # 工具类
 │   │                     # 通用工具：日期处理、加密、文件操作、常量定义
 │   ├── exceptions        # 全局异常处理
 │   │                     # 自定义异常类、全局异常捕获中间件
 │   ├── middleware         # 中间件（对应Interceptor）
 │   │                     # 登录鉴权、Token校验、请求日志、限流等
 │   ├── dependencies      # 依赖注入（Python特有，对应Annotation/部分Config）
 │   │                     # 数据库会话获取、当前用户获取、权限校验等可复用依赖
 │   └── common            # 公共模块
 │                         # 统一响应格式、枚举类、全局常量
 ├── tests                 # 测试目录
 │   ├── unit              # 单元测试
 │   └── integration       # 集成测试
 ├── requirements.txt / pyproject.toml  # 依赖管理
 └── .env                  # 环境变量配置文件
 ```