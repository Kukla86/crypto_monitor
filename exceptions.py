#!/usr/bin/env python3
"""
Кастомные исключения для системы мониторинга криптовалют
"""

from typing import Optional, Dict, Any


class CryptoMonitorError(Exception):
    """Базовое исключение для системы мониторинга криптовалют"""
    
    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.context = context or {}
    
    def __str__(self):
        context_str = f" | Context: {self.context}" if self.context else ""
        return f"{self.__class__.__name__}: {self.message}{context_str}"


class APIError(CryptoMonitorError):
    """Ошибка API запроса"""
    
    def __init__(self, message: str, api_name: str, status_code: Optional[int] = None, 
                 response_data: Optional[Dict[str, Any]] = None):
        context = {
            'api_name': api_name,
            'status_code': status_code,
            'response_data': response_data
        }
        super().__init__(message, context)


class RateLimitError(APIError):
    """Ошибка превышения лимита запросов к API"""
    
    def __init__(self, api_name: str, retry_after: Optional[int] = None):
        message = f"Rate limit exceeded for {api_name}"
        if retry_after:
            message += f", retry after {retry_after} seconds"
        
        context = {
            'api_name': api_name,
            'retry_after': retry_after,
            'error_type': 'rate_limit'
        }
        super().__init__(message, context)


class NetworkError(CryptoMonitorError):
    """Ошибка сети (таймаут, соединение и т.д.)"""
    
    def __init__(self, message: str, url: str, timeout: Optional[float] = None):
        context = {
            'url': url,
            'timeout': timeout,
            'error_type': 'network'
        }
        super().__init__(message, context)


class DatabaseError(CryptoMonitorError):
    """Ошибка базы данных"""
    
    def __init__(self, message: str, operation: str, table: Optional[str] = None):
        context = {
            'operation': operation,
            'table': table,
            'error_type': 'database'
        }
        super().__init__(message, context)


class ConfigurationError(CryptoMonitorError):
    """Ошибка конфигурации"""
    
    def __init__(self, message: str, config_key: Optional[str] = None, 
                 expected_type: Optional[str] = None):
        context = {
            'config_key': config_key,
            'expected_type': expected_type,
            'error_type': 'configuration'
        }
        super().__init__(message, context)


class TokenError(CryptoMonitorError):
    """Ошибка, связанная с токеном"""
    
    def __init__(self, message: str, token_symbol: str, chain: Optional[str] = None):
        context = {
            'token_symbol': token_symbol,
            'chain': chain,
            'error_type': 'token'
        }
        super().__init__(message, context)


class SocialMediaError(CryptoMonitorError):
    """Ошибка социальных сетей"""
    
    def __init__(self, message: str, platform: str, account: Optional[str] = None):
        context = {
            'platform': platform,
            'account': account,
            'error_type': 'social_media'
        }
        super().__init__(message, context)


class AlertError(CryptoMonitorError):
    """Ошибка отправки алертов"""
    
    def __init__(self, message: str, alert_type: str, recipient: Optional[str] = None):
        context = {
            'alert_type': alert_type,
            'recipient': recipient,
            'error_type': 'alert'
        }
        super().__init__(message, context)


class DataValidationError(CryptoMonitorError):
    """Ошибка валидации данных"""
    
    def __init__(self, message: str, data_type: str, field: Optional[str] = None, 
                 value: Optional[Any] = None):
        context = {
            'data_type': data_type,
            'field': field,
            'value': value,
            'error_type': 'validation'
        }
        super().__init__(message, context)


class RetryableError(CryptoMonitorError):
    """Ошибка, которую можно повторить"""
    
    def __init__(self, message: str, max_retries: int = 3, retry_delay: float = 1.0):
        context = {
            'max_retries': max_retries,
            'retry_delay': retry_delay,
            'error_type': 'retryable'
        }
        super().__init__(message, context)


class CriticalError(CryptoMonitorError):
    """Критическая ошибка, требующая немедленного внимания"""
    
    def __init__(self, message: str, component: str, severity: str = 'critical'):
        context = {
            'component': component,
            'severity': severity,
            'error_type': 'critical'
        }
        super().__init__(message, context)


# Функции для создания исключений с контекстом
def create_api_error(api_name: str, status_code: int, response_data: Optional[Dict[str, Any]] = None) -> APIError:
    """Создает APIError с автоматическим сообщением"""
    message = f"API {api_name} returned status {status_code}"
    if response_data and 'error' in response_data:
        message += f": {response_data['error']}"
    return APIError(message, api_name, status_code, response_data)


def create_rate_limit_error(api_name: str, retry_after: Optional[int] = None) -> RateLimitError:
    """Создает RateLimitError"""
    return RateLimitError(api_name, retry_after)


def create_network_error(url: str, timeout: Optional[float] = None, 
                        original_error: Optional[Exception] = None) -> NetworkError:
    """Создает NetworkError с информацией об исходной ошибке"""
    message = f"Network error for {url}"
    if original_error:
        message += f": {str(original_error)}"
    return NetworkError(message, url, timeout)


def create_database_error(operation: str, table: Optional[str] = None, 
                         original_error: Optional[Exception] = None) -> DatabaseError:
    """Создает DatabaseError"""
    message = f"Database error during {operation}"
    if table:
        message += f" on table {table}"
    if original_error:
        message += f": {str(original_error)}"
    return DatabaseError(message, operation, table)


def create_configuration_error(config_key: str, expected_type: Optional[str] = None,
                              actual_value: Optional[Any] = None) -> ConfigurationError:
    """Создает ConfigurationError"""
    message = f"Configuration error for {config_key}"
    if expected_type and actual_value is not None:
        message += f": expected {expected_type}, got {type(actual_value).__name__}"
    return ConfigurationError(message, config_key, expected_type)


def create_token_error(token_symbol: str, message: str, chain: Optional[str] = None) -> TokenError:
    """Создает TokenError"""
    return TokenError(message, token_symbol, chain)


def create_social_media_error(platform: str, message: str, account: Optional[str] = None) -> SocialMediaError:
    """Создает SocialMediaError"""
    return SocialMediaError(message, platform, account)


def create_alert_error(alert_type: str, message: str, recipient: Optional[str] = None) -> AlertError:
    """Создает AlertError"""
    return AlertError(message, alert_type, recipient)


def create_validation_error(data_type: str, field: str, value: Any, 
                           expected_format: Optional[str] = None) -> DataValidationError:
    """Создает DataValidationError"""
    message = f"Validation error for {data_type}.{field}: invalid value {value}"
    if expected_format:
        message += f", expected format: {expected_format}"
    return DataValidationError(message, data_type, field, value)


def create_critical_error(component: str, message: str, severity: str = 'critical') -> CriticalError:
    """Создает CriticalError"""
    return CriticalError(message, component, severity)


# Функции для проверки типов ошибок
def is_retryable_error(error: Exception) -> bool:
    """Проверяет, является ли ошибка повторяемой"""
    return isinstance(error, (RetryableError, NetworkError, RateLimitError))


def is_critical_error(error: Exception) -> bool:
    """Проверяет, является ли ошибка критической"""
    return isinstance(error, CriticalError)


def is_api_error(error: Exception) -> bool:
    """Проверяет, является ли ошибка API ошибкой"""
    return isinstance(error, (APIError, RateLimitError))


def get_error_context(error: Exception) -> Dict[str, Any]:
    """Получает контекст ошибки"""
    if isinstance(error, CryptoMonitorError):
        return error.context
    return {'error_type': type(error).__name__, 'message': str(error)}


def format_error_message(error: Exception) -> str:
    """Форматирует сообщение об ошибке для логирования"""
    if isinstance(error, CryptoMonitorError):
        context_str = ""
        if error.context:
            context_items = [f"{k}={v}" for k, v in error.context.items() if v is not None]
            if context_items:
                context_str = f" | Context: {', '.join(context_items)}"
        return f"{error.__class__.__name__}: {error.message}{context_str}"
    return f"{type(error).__name__}: {str(error)}" 