from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

from config import DATABASE_FILE

# Создание движка для подключения к базе данных
engine = create_engine(f"sqlite:///{DATABASE_FILE}")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Модель для хранения пользователей
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(String, unique=True, index=True)
    tracked_flights = relationship("TrackedFlight", back_populates="user")

# Модель для отслеживаемых рейсов
class TrackedFlight(Base):
    __tablename__ = "tracked_flights"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    origin = Column(String, index=True)
    destination = Column(String, index=True)
    departure_date = Column(String)
    return_date = Column(String)
    price_threshold = Column(Float)
    notified = Column(Boolean, default=False)
    
    user = relationship("User", back_populates="tracked_flights")

# Функция для создания таблиц в базе данных
def init_db():
    Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    init_db()
    print("База данных инициализирована.")
