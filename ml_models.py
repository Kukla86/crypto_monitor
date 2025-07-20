#!/usr/bin/env python3
"""
Модуль машинного обучения для системы мониторинга криптовалют
Включает предсказание цен, анализ настроений и обнаружение аномалий
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
import logging
from sklearn.ensemble import RandomForestRegressor, IsolationForest
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler, MinMaxScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline
import joblib
import json
import os
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

logger = logging.getLogger(__name__)

class PricePredictor:
    """Модель для предсказания цен криптовалют"""
    
    def __init__(self, model_type: str = 'random_forest'):
        """
        Инициализация предиктора цен
        
        Args:
            model_type: Тип модели ('random_forest', 'linear', 'ensemble')
        """
        self.model_type = model_type
        self.model = None
        self.scaler = StandardScaler()
        self.feature_names = []
        self.is_trained = False
        self.models_dir = Path('models')
        self.models_dir.mkdir(exist_ok=True)
        
        self._initialize_model()
    
    def _initialize_model(self):
        """Инициализация модели"""
        if self.model_type == 'random_forest':
            self.model = RandomForestRegressor(
                n_estimators=100,
                max_depth=10,
                random_state=42,
                n_jobs=-1
            )
        elif self.model_type == 'linear':
            self.model = LinearRegression()
        elif self.model_type == 'ensemble':
            self.model = RandomForestRegressor(
                n_estimators=200,
                max_depth=15,
                random_state=42,
                n_jobs=-1
            )
        else:
            raise ValueError(f"Неизвестный тип модели: {self.model_type}")
    
    def prepare_features(self, price_data: List[float], volume_data: List[float] = None) -> np.ndarray:
        """
        Подготовка признаков для модели
        
        Args:
            price_data: Исторические цены
            volume_data: Исторические объемы (опционально)
            
        Returns:
            Массив признаков
        """
        if len(price_data) < 20:
            raise ValueError("Недостаточно данных для создания признаков")
        
        features = []
        
        # Технические индикаторы
        prices = np.array(price_data)
        
        # Простые скользящие средние
        for window in [5, 10, 20]:
            if len(prices) >= window:
                sma = np.mean(prices[-window:])
                features.append(sma)
            else:
                features.append(prices[-1])
        
        # Изменения цен
        for period in [1, 5, 10]:
            if len(prices) > period:
                change = (prices[-1] - prices[-period-1]) / prices[-period-1]
                features.append(change)
            else:
                features.append(0.0)
        
        # Волатильность
        if len(prices) >= 10:
            volatility = np.std(prices[-10:])
            features.append(volatility)
        else:
            features.append(0.0)
        
        # RSI
        if len(prices) >= 14:
            rsi = self._calculate_rsi(prices, 14)
            features.append(rsi)
        else:
            features.append(50.0)
        
        # Объемные данные
        if volume_data and len(volume_data) >= 10:
            volume_avg = np.mean(volume_data[-10:])
            features.append(volume_avg)
            
            volume_change = (volume_data[-1] - volume_data[-5]) / volume_data[-5] if volume_data[-5] > 0 else 0
            features.append(volume_change)
        else:
            features.append(0.0)
            features.append(0.0)
        
        # Временные признаки
        now = datetime.now()
        features.extend([
            now.hour / 24.0,  # Час дня
            now.weekday() / 7.0,  # День недели
            now.month / 12.0  # Месяц
        ])
        
        return np.array(features).reshape(1, -1)
    
    def _calculate_rsi(self, prices: np.ndarray, period: int = 14) -> float:
        """Расчет RSI"""
        if len(prices) < period + 1:
            return 50.0
        
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def train(self, symbol: str, price_history: List[float], volume_history: List[float] = None, 
              target_hours: int = 24) -> Dict[str, float]:
        """
        Обучение модели
        
        Args:
            symbol: Символ токена
            price_history: Исторические цены
            volume_history: Исторические объемы
            target_hours: Целевой горизонт предсказания в часах
            
        Returns:
            Метрики качества модели
        """
        if len(price_history) < 50:
            raise ValueError("Недостаточно данных для обучения (минимум 50 точек)")
        
        # Подготовка данных
        X, y = [], []
        
        for i in range(20, len(price_history) - target_hours):
            # Признаки
            price_window = price_history[i-20:i]
            volume_window = volume_history[i-20:i] if volume_history else None
            
            features = self.prepare_features(price_window, volume_window)
            X.append(features.flatten())
            
            # Целевая переменная (изменение цены через target_hours часов)
            current_price = price_history[i]
            future_price = price_history[i + target_hours]
            price_change = (future_price - current_price) / current_price
            y.append(price_change)
        
        X = np.array(X)
        y = np.array(y)
        
        # Разделение на обучающую и тестовую выборки
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )
        
        # Масштабирование признаков
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        # Обучение модели
        self.model.fit(X_train_scaled, y_train)
        
        # Предсказания
        y_pred_train = self.model.predict(X_train_scaled)
        y_pred_test = self.model.predict(X_test_scaled)
        
        # Метрики качества
        metrics = {
            'train_mse': mean_squared_error(y_train, y_pred_train),
            'test_mse': mean_squared_error(y_test, y_pred_test),
            'train_mae': mean_absolute_error(y_train, y_pred_train),
            'test_mae': mean_absolute_error(y_test, y_pred_test),
            'train_r2': r2_score(y_train, y_pred_train),
            'test_r2': r2_score(y_test, y_pred_test)
        }
        
        self.is_trained = True
        self.feature_names = [f'feature_{i}' for i in range(X.shape[1])]
        
        # Сохранение модели
        self.save_model(symbol)
        
        logger.info(f"Модель для {symbol} обучена. Test R²: {metrics['test_r2']:.4f}")
        
        return metrics
    
    def predict(self, symbol: str, price_history: List[float], volume_history: List[float] = None,
                hours_ahead: int = 24) -> Dict[str, Any]:
        """
        Предсказание изменения цены
        
        Args:
            symbol: Символ токена
            price_history: Исторические цены
            volume_history: Исторические объемы
            hours_ahead: Горизонт предсказания в часах
            
        Returns:
            Результат предсказания
        """
        if not self.is_trained:
            # Попытка загрузить сохраненную модель
            if not self.load_model(symbol):
                raise ValueError(f"Модель для {symbol} не обучена и не найдена")
        
        # Подготовка признаков
        features = self.prepare_features(price_history, volume_history)
        features_scaled = self.scaler.transform(features)
        
        # Предсказание
        prediction = self.model.predict(features_scaled)[0]
        
        # Доверительный интервал (для Random Forest)
        if hasattr(self.model, 'estimators_'):
            predictions = []
            for estimator in self.model.estimators_:
                pred = estimator.predict(features_scaled)[0]
                predictions.append(pred)
            
            confidence_interval = np.percentile(predictions, [5, 95])
        else:
            confidence_interval = [prediction * 0.9, prediction * 1.1]
        
        current_price = price_history[-1]
        predicted_price = current_price * (1 + prediction)
        
        result = {
            'symbol': symbol,
            'current_price': current_price,
            'predicted_change': prediction,
            'predicted_price': predicted_price,
            'confidence_lower': current_price * (1 + confidence_interval[0]),
            'confidence_upper': current_price * (1 + confidence_interval[1]),
            'prediction_hours': hours_ahead,
            'model_type': self.model_type,
            'timestamp': datetime.now().isoformat()
        }
        
        return result
    
    def save_model(self, symbol: str):
        """Сохранение модели"""
        model_path = self.models_dir / f"{symbol}_price_model.pkl"
        scaler_path = self.models_dir / f"{symbol}_scaler.pkl"
        
        model_data = {
            'model': self.model,
            'scaler': self.scaler,
            'feature_names': self.feature_names,
            'model_type': self.model_type,
            'trained_at': datetime.now().isoformat()
        }
        
        joblib.dump(model_data, model_path)
        logger.info(f"Модель для {symbol} сохранена в {model_path}")
    
    def load_model(self, symbol: str) -> bool:
        """Загрузка модели"""
        model_path = self.models_dir / f"{symbol}_price_model.pkl"
        
        if not model_path.exists():
            return False
        
        try:
            model_data = joblib.load(model_path)
            self.model = model_data['model']
            self.scaler = model_data['scaler']
            self.feature_names = model_data['feature_names']
            self.model_type = model_data['model_type']
            self.is_trained = True
            
            logger.info(f"Модель для {symbol} загружена")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка загрузки модели для {symbol}: {e}")
            return False

class SentimentAnalyzer:
    """Анализатор настроений для социальных сетей"""
    
    def __init__(self):
        """Инициализация анализатора настроений"""
        self.vectorizer = TfidfVectorizer(
            max_features=5000,
            stop_words='english',
            ngram_range=(1, 2)
        )
        
        self.classifier = MultinomialNB()
        self.pipeline = Pipeline([
            ('vectorizer', self.vectorizer),
            ('classifier', self.classifier)
        ])
        
        self.is_trained = False
        self.models_dir = Path('models')
        self.models_dir.mkdir(exist_ok=True)
        
        # Словари настроений
        self.positive_words = {
            'moon', 'pump', 'bullish', 'buy', 'hodl', 'diamond', 'rocket',
            'gains', 'profit', 'success', 'win', 'great', 'amazing', 'awesome'
        }
        
        self.negative_words = {
            'dump', 'bearish', 'sell', 'crash', 'rug', 'scam', 'fake',
            'loss', 'fail', 'terrible', 'awful', 'bad', 'worst', 'dead'
        }
    
    def analyze_text(self, text: str) -> Dict[str, float]:
        """
        Анализ настроения текста
        
        Args:
            text: Текст для анализа
            
        Returns:
            Словарь с оценками настроений
        """
        if not text or len(text.strip()) == 0:
            return {'positive': 0.0, 'negative': 0.0, 'neutral': 1.0}
        
        # Простой анализ на основе ключевых слов
        text_lower = text.lower()
        words = text_lower.split()
        
        positive_count = sum(1 for word in words if word in self.positive_words)
        negative_count = sum(1 for word in words if word in self.negative_words)
        
        total_words = len(words)
        
        if total_words == 0:
            return {'positive': 0.0, 'negative': 0.0, 'neutral': 1.0}
        
        positive_score = positive_count / total_words
        negative_score = negative_count / total_words
        neutral_score = 1.0 - positive_score - negative_score
        
        # Нормализация
        total = positive_score + negative_score + neutral_score
        if total > 0:
            positive_score /= total
            negative_score /= total
            neutral_score /= total
        
        return {
            'positive': positive_score,
            'negative': negative_score,
            'neutral': neutral_score
        }
    
    def train(self, texts: List[str], labels: List[str]) -> Dict[str, float]:
        """
        Обучение модели анализа настроений
        
        Args:
            texts: Список текстов
            labels: Список меток ('positive', 'negative', 'neutral')
            
        Returns:
            Метрики качества
        """
        if len(texts) != len(labels):
            raise ValueError("Количество текстов и меток должно совпадать")
        
        # Разделение на обучающую и тестовую выборки
        X_train, X_test, y_train, y_test = train_test_split(
            texts, labels, test_size=0.2, random_state=42
        )
        
        # Обучение модели
        self.pipeline.fit(X_train, y_train)
        
        # Предсказания
        y_pred = self.pipeline.predict(X_test)
        
        # Метрики качества
        from sklearn.metrics import classification_report, accuracy_score
        
        accuracy = accuracy_score(y_test, y_pred)
        report = classification_report(y_test, y_pred, output_dict=True)
        
        self.is_trained = True
        
        # Сохранение модели
        self.save_model()
        
        logger.info(f"Модель анализа настроений обучена. Точность: {accuracy:.4f}")
        
        return {
            'accuracy': accuracy,
            'classification_report': report
        }
    
    def predict_sentiment(self, text: str) -> str:
        """
        Предсказание настроения текста
        
        Args:
            text: Текст для анализа
            
        Returns:
            Метка настроения
        """
        if not self.is_trained:
            # Попытка загрузить сохраненную модель
            if not self.load_model():
                # Используем простой анализ
                sentiment = self.analyze_text(text)
                return max(sentiment, key=sentiment.get)
        
        prediction = self.pipeline.predict([text])[0]
        return prediction
    
    def save_model(self):
        """Сохранение модели"""
        model_path = self.models_dir / "sentiment_model.pkl"
        joblib.dump(self.pipeline, model_path)
        logger.info(f"Модель анализа настроений сохранена в {model_path}")
    
    def load_model(self) -> bool:
        """Загрузка модели"""
        model_path = self.models_dir / "sentiment_model.pkl"
        
        if not model_path.exists():
            return False
        
        try:
            self.pipeline = joblib.load(model_path)
            self.is_trained = True
            logger.info("Модель анализа настроений загружена")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка загрузки модели анализа настроений: {e}")
            return False

class AnomalyDetector:
    """Детектор аномалий для обнаружения необычных паттернов"""
    
    def __init__(self, contamination: float = 0.1):
        """
        Инициализация детектора аномалий
        
        Args:
            contamination: Доля аномалий в данных
        """
        self.model = IsolationForest(
            contamination=contamination,
            random_state=42,
            n_estimators=100
        )
        self.scaler = StandardScaler()
        self.is_trained = False
        self.models_dir = Path('models')
        self.models_dir.mkdir(exist_ok=True)
    
    def prepare_features(self, price_data: List[float], volume_data: List[float] = None) -> np.ndarray:
        """
        Подготовка признаков для детекции аномалий
        
        Args:
            price_data: Исторические цены
            volume_data: Исторические объемы
            
        Returns:
            Массив признаков
        """
        if len(price_data) < 10:
            raise ValueError("Недостаточно данных для детекции аномалий")
        
        features = []
        prices = np.array(price_data)
        
        # Изменения цен
        price_changes = np.diff(prices)
        features.extend([
            np.mean(price_changes[-5:]),
            np.std(price_changes[-5:]),
            np.max(price_changes[-5:]),
            np.min(price_changes[-5:])
        ])
        
        # Волатильность
        features.append(np.std(prices[-10:]))
        
        # Отклонение от среднего
        mean_price = np.mean(prices[-20:])
        features.append((prices[-1] - mean_price) / mean_price if mean_price > 0 else 0)
        
        # Объемные данные
        if volume_data and len(volume_data) >= 10:
            volumes = np.array(volume_data)
            features.extend([
                np.mean(volumes[-5:]),
                np.std(volumes[-5:]),
                (volumes[-1] - np.mean(volumes[-10:])) / np.mean(volumes[-10:]) if np.mean(volumes[-10:]) > 0 else 0
            ])
        else:
            features.extend([0.0, 0.0, 0.0])
        
        return np.array(features).reshape(1, -1)
    
    def train(self, price_data: List[List[float]], volume_data: List[List[float]] = None) -> Dict[str, Any]:
        """
        Обучение детектора аномалий
        
        Args:
            price_data: Список исторических данных цен
            volume_data: Список исторических данных объемов
            
        Returns:
            Метрики обучения
        """
        if len(price_data) < 10:
            raise ValueError("Недостаточно данных для обучения детектора аномалий")
        
        # Подготовка признаков
        X = []
        for i, prices in enumerate(price_data):
            volumes = volume_data[i] if volume_data else None
            features = self.prepare_features(prices, volumes)
            X.append(features.flatten())
        
        X = np.array(X)
        
        # Масштабирование
        X_scaled = self.scaler.fit_transform(X)
        
        # Обучение модели
        self.model.fit(X_scaled)
        
        # Предсказания
        predictions = self.model.predict(X_scaled)
        anomaly_scores = self.model.decision_function(X_scaled)
        
        # Статистика
        n_anomalies = np.sum(predictions == -1)
        anomaly_rate = n_anomalies / len(predictions)
        
        self.is_trained = True
        
        # Сохранение модели
        self.save_model()
        
        logger.info(f"Детектор аномалий обучен. Найдено аномалий: {n_anomalies}/{len(predictions)} ({anomaly_rate:.2%})")
        
        return {
            'total_samples': len(predictions),
            'anomalies_detected': n_anomalies,
            'anomaly_rate': anomaly_rate,
            'mean_anomaly_score': np.mean(anomaly_scores)
        }
    
    def detect_anomaly(self, price_data: List[float], volume_data: List[float] = None) -> Dict[str, Any]:
        """
        Детекция аномалий в данных
        
        Args:
            price_data: Исторические цены
            volume_data: Исторические объемы
            
        Returns:
            Результат детекции
        """
        if not self.is_trained:
            # Попытка загрузить сохраненную модель
            if not self.load_model():
                raise ValueError("Детектор аномалий не обучен и не найден")
        
        # Подготовка признаков
        features = self.prepare_features(price_data, volume_data)
        features_scaled = self.scaler.transform(features)
        
        # Предсказание
        prediction = self.model.predict(features_scaled)[0]
        anomaly_score = self.model.decision_function(features_scaled)[0]
        
        # Интерпретация результата
        is_anomaly = prediction == -1
        confidence = abs(anomaly_score)
        
        if is_anomaly:
            if anomaly_score < -0.5:
                severity = "high"
            elif anomaly_score < -0.2:
                severity = "medium"
            else:
                severity = "low"
        else:
            severity = "none"
        
        return {
            'is_anomaly': is_anomaly,
            'anomaly_score': anomaly_score,
            'confidence': confidence,
            'severity': severity,
            'timestamp': datetime.now().isoformat()
        }
    
    def save_model(self):
        """Сохранение модели"""
        model_path = self.models_dir / "anomaly_detector.pkl"
        scaler_path = self.models_dir / "anomaly_scaler.pkl"
        
        model_data = {
            'model': self.model,
            'scaler': self.scaler,
            'trained_at': datetime.now().isoformat()
        }
        
        joblib.dump(model_data, model_path)
        logger.info(f"Детектор аномалий сохранен в {model_path}")
    
    def load_model(self) -> bool:
        """Загрузка модели"""
        model_path = self.models_dir / "anomaly_detector.pkl"
        
        if not model_path.exists():
            return False
        
        try:
            model_data = joblib.load(model_path)
            self.model = model_data['model']
            self.scaler = model_data['scaler']
            self.is_trained = True
            
            logger.info("Детектор аномалий загружен")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка загрузки детектора аномалий: {e}")
            return False

class MLManager:
    """Менеджер машинного обучения для координации всех моделей"""
    
    def __init__(self):
        """Инициализация менеджера ML"""
        self.price_predictor = PricePredictor()
        self.sentiment_analyzer = SentimentAnalyzer()
        self.anomaly_detector = AnomalyDetector()
        
        self.models_dir = Path('models')
        self.models_dir.mkdir(exist_ok=True)
    
    def analyze_token(self, symbol: str, price_data: List[float], volume_data: List[float] = None,
                     social_data: List[str] = None) -> Dict[str, Any]:
        """
        Комплексный анализ токена
        
        Args:
            symbol: Символ токена
            price_data: Исторические цены
            volume_data: Исторические объемы
            social_data: Данные из социальных сетей
            
        Returns:
            Результаты комплексного анализа
        """
        results = {
            'symbol': symbol,
            'timestamp': datetime.now().isoformat(),
            'price_prediction': None,
            'sentiment_analysis': None,
            'anomaly_detection': None,
            'overall_score': 0.0
        }
        
        try:
            # Предсказание цены
            if len(price_data) >= 20:
                price_pred = self.price_predictor.predict(symbol, price_data, volume_data)
                results['price_prediction'] = price_pred
                
                # Оценка на основе предсказания
                if price_pred['predicted_change'] > 0.05:  # +5%
                    results['overall_score'] += 0.3
                elif price_pred['predicted_change'] < -0.05:  # -5%
                    results['overall_score'] -= 0.3
            
            # Анализ настроений
            if social_data and len(social_data) > 0:
                sentiments = []
                for text in social_data[:10]:  # Анализируем последние 10 сообщений
                    sentiment = self.sentiment_analyzer.analyze_text(text)
                    sentiments.append(sentiment)
                
                # Среднее настроение
                avg_sentiment = {
                    'positive': np.mean([s['positive'] for s in sentiments]),
                    'negative': np.mean([s['negative'] for s in sentiments]),
                    'neutral': np.mean([s['neutral'] for s in sentiments])
                }
                
                results['sentiment_analysis'] = {
                    'average_sentiment': avg_sentiment,
                    'messages_analyzed': len(sentiments),
                    'dominant_sentiment': max(avg_sentiment, key=avg_sentiment.get)
                }
                
                # Оценка на основе настроений
                if avg_sentiment['positive'] > 0.6:
                    results['overall_score'] += 0.2
                elif avg_sentiment['negative'] > 0.6:
                    results['overall_score'] -= 0.2
            
            # Детекция аномалий
            if len(price_data) >= 10:
                anomaly = self.anomaly_detector.detect_anomaly(price_data, volume_data)
                results['anomaly_detection'] = anomaly
                
                # Оценка на основе аномалий
                if anomaly['is_anomaly']:
                    if anomaly['severity'] == 'high':
                        results['overall_score'] -= 0.3
                    elif anomaly['severity'] == 'medium':
                        results['overall_score'] -= 0.1
            
            # Нормализация общего скора
            results['overall_score'] = max(-1.0, min(1.0, results['overall_score']))
            
            # Интерпретация скора
            if results['overall_score'] > 0.3:
                results['recommendation'] = 'buy'
            elif results['overall_score'] < -0.3:
                results['recommendation'] = 'sell'
            else:
                results['recommendation'] = 'hold'
            
        except Exception as e:
            logger.error(f"Ошибка анализа токена {symbol}: {e}")
            results['error'] = str(e)
        
        return results
    
    def train_all_models(self, training_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Обучение всех моделей
        
        Args:
            training_data: Данные для обучения
            
        Returns:
            Результаты обучения
        """
        results = {}
        
        try:
            # Обучение предиктора цен
            if 'price_data' in training_data:
                for symbol, data in training_data['price_data'].items():
                    metrics = self.price_predictor.train(
                        symbol, 
                        data['prices'], 
                        data.get('volumes')
                    )
                    results[f'price_predictor_{symbol}'] = metrics
            
            # Обучение анализатора настроений
            if 'sentiment_data' in training_data:
                metrics = self.sentiment_analyzer.train(
                    training_data['sentiment_data']['texts'],
                    training_data['sentiment_data']['labels']
                )
                results['sentiment_analyzer'] = metrics
            
            # Обучение детектора аномалий
            if 'anomaly_data' in training_data:
                metrics = self.anomaly_detector.train(
                    training_data['anomaly_data']['price_data'],
                    training_data['anomaly_data'].get('volume_data')
                )
                results['anomaly_detector'] = metrics
            
            logger.info("Все модели успешно обучены")
            
        except Exception as e:
            logger.error(f"Ошибка обучения моделей: {e}")
            results['error'] = str(e)
        
        return results
    
    def get_model_status(self) -> Dict[str, Any]:
        """Получение статуса всех моделей"""
        return {
            'price_predictor': {
                'trained': self.price_predictor.is_trained,
                'model_type': self.price_predictor.model_type
            },
            'sentiment_analyzer': {
                'trained': self.sentiment_analyzer.is_trained
            },
            'anomaly_detector': {
                'trained': self.anomaly_detector.is_trained
            }
        }

# Глобальный экземпляр менеджера ML
ml_manager = None

def get_ml_manager() -> MLManager:
    """Получение глобального менеджера ML"""
    global ml_manager
    if ml_manager is None:
        ml_manager = MLManager()
    return ml_manager 