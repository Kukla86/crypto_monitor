#!/usr/bin/env python3
"""
Модуль управления процессами мониторинга криптовалют
Позволяет запускать/останавливать скрипты через Telegram бот
"""

import os
import sys
import psutil
import subprocess
import logging
import json
import time
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

class ProcessManager:
    """Менеджер процессов для управления скриптами мониторинга"""
    
    def __init__(self):
        self.project_dir = Path(__file__).parent
        self.processes_file = self.project_dir / "running_processes.json"
        self.logs_dir = self.project_dir / "logs"
        self.logs_dir.mkdir(exist_ok=True)
        
        # Конфигурация скриптов
        self.scripts = {
            'monitor': {
                'name': 'Crypto Monitor',
                'script': 'monitor.py',
                'description': 'Основной скрипт мониторинга криптовалют',
                'args': [],
                'auto_restart': True,
                'restart_delay': 30
            },
            'telegram_bot': {
                'name': 'Telegram Bot',
                'script': 'telegram_bot.py', 
                'description': 'Telegram бот для управления',
                'args': [],
                'auto_restart': False,  # Отключен автоматический запуск
                'restart_delay': 10
            },
            'web_dashboard': {
                'name': 'Web Dashboard',
                'script': 'web_dashboard.py',
                'description': 'Веб-интерфейс мониторинга',
                'args': [],
                'auto_restart': True,
                'restart_delay': 60
            }
        }
        
        self.load_running_processes()
    
    def load_running_processes(self):
        """Загрузка информации о запущенных процессах"""
        try:
            if self.processes_file.exists():
                with open(self.processes_file, 'r') as f:
                    self.running_processes = json.load(f)
            else:
                self.running_processes = {}
        except Exception as e:
            logger.error(f"Ошибка загрузки процессов: {e}")
            self.running_processes = {}
    
    def save_running_processes(self):
        """Сохранение информации о запущенных процессах"""
        try:
            with open(self.processes_file, 'w') as f:
                json.dump(self.running_processes, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Ошибка сохранения процессов: {e}")
    
    def get_process_info(self, pid: int) -> Optional[Dict]:
        """Получение информации о процессе по PID"""
        try:
            process = psutil.Process(pid)
            return {
                'pid': pid,
                'name': process.name(),
                'cmdline': ' '.join(process.cmdline()),
                'status': process.status(),
                'cpu_percent': process.cpu_percent(),
                'memory_mb': process.memory_info().rss / 1024 / 1024,
                'create_time': process.create_time(),
                'running_time': time.time() - process.create_time()
            }
        except psutil.NoSuchProcess:
            return None
        except Exception as e:
            logger.error(f"Ошибка получения информации о процессе {pid}: {e}")
            return None
    
    def is_process_running(self, script_name: str) -> bool:
        """Проверка, запущен ли процесс"""
        if script_name not in self.running_processes:
            return False
        
        pid = self.running_processes[script_name].get('pid')
        if not pid:
            return False
        
        try:
            process = psutil.Process(pid)
            return process.is_running()
        except psutil.NoSuchProcess:
            return False
    
    def start_script(self, script_name: str, user_id: int = None) -> Tuple[bool, str]:
        """Запуск скрипта"""
        try:
            if script_name not in self.scripts:
                return False, f"Скрипт {script_name} не найден"
            
            if self.is_process_running(script_name):
                return False, f"Скрипт {script_name} уже запущен"
            
            script_config = self.scripts[script_name]
            script_path = self.project_dir / script_config['script']
            
            if not script_path.exists():
                return False, f"Файл {script_config['script']} не найден"
            
            # Подготавливаем команду
            cmd = [sys.executable, str(script_path)] + script_config['args']
            
            # Настраиваем логирование
            log_file = self.logs_dir / f"{script_name}.log"
            with open(log_file, 'a') as log:
                # Запускаем процесс
                process = subprocess.Popen(
                    cmd,
                    stdout=log,
                    stderr=log,
                    cwd=self.project_dir,
                    preexec_fn=os.setsid if os.name != 'nt' else None
                )
            
            # Сохраняем информацию о процессе
            self.running_processes[script_name] = {
                'pid': process.pid,
                'started_at': datetime.now().isoformat(),
                'started_by': user_id,
                'script': script_config['script'],
                'args': script_config['args'],
                'log_file': str(log_file),
                'auto_restart': script_config['auto_restart']
            }
            
            self.save_running_processes()
            
            logger.info(f"Скрипт {script_name} запущен с PID {process.pid}")
            return True, f"Скрипт {script_name} запущен (PID: {process.pid})"
            
        except Exception as e:
            logger.error(f"Ошибка запуска скрипта {script_name}: {e}")
            return False, f"Ошибка запуска: {str(e)}"
    
    def stop_script(self, script_name: str, user_id: int = None) -> Tuple[bool, str]:
        """Остановка скрипта"""
        try:
            if not self.is_process_running(script_name):
                return False, f"Скрипт {script_name} не запущен"
            
            pid = self.running_processes[script_name]['pid']
            
            # Пытаемся остановить процесс
            try:
                process = psutil.Process(pid)
                
                # Сначала пробуем graceful shutdown
                process.terminate()
                process.wait(timeout=10)
                
            except psutil.TimeoutExpired:
                # Если не остановился, убиваем принудительно
                process.kill()
                logger.warning(f"Принудительная остановка процесса {pid}")
                
            except psutil.NoSuchProcess:
                logger.info(f"Процесс {pid} уже завершен")
            
            # Удаляем из списка запущенных
            if script_name in self.running_processes:
                del self.running_processes[script_name]
                self.save_running_processes()
            
            logger.info(f"Скрипт {script_name} остановлен")
            return True, f"Скрипт {script_name} остановлен"
            
        except Exception as e:
            logger.error(f"Ошибка остановки скрипта {script_name}: {e}")
            return False, f"Ошибка остановки: {str(e)}"
    
    def restart_script(self, script_name: str, user_id: int = None) -> Tuple[bool, str]:
        """Перезапуск скрипта"""
        try:
            # Останавливаем если запущен
            if self.is_process_running(script_name):
                stop_success, stop_msg = self.stop_script(script_name, user_id)
                if not stop_success:
                    return False, f"Не удалось остановить: {stop_msg}"
                
                # Небольшая пауза
                time.sleep(2)
            
            # Запускаем заново
            start_success, start_msg = self.start_script(script_name, user_id)
            if not start_success:
                return False, f"Не удалось запустить: {start_msg}"
            
            return True, f"Скрипт {script_name} перезапущен"
            
        except Exception as e:
            logger.error(f"Ошибка перезапуска скрипта {script_name}: {e}")
            return False, f"Ошибка перезапуска: {str(e)}"
    
    def get_status(self) -> Dict:
        """Получение статуса всех скриптов"""
        status = {
            'scripts': {},
            'summary': {
                'total': len(self.scripts),
                'running': 0,
                'stopped': 0
            }
        }
        
        for script_name, config in self.scripts.items():
            is_running = self.is_process_running(script_name)
            process_info = None
            
            if is_running:
                pid = self.running_processes[script_name]['pid']
                process_info = self.get_process_info(pid)
                status['summary']['running'] += 1
            else:
                status['summary']['stopped'] += 1
            
            status['scripts'][script_name] = {
                'name': config['name'],
                'description': config['description'],
                'running': is_running,
                'process_info': process_info,
                'config': {
                    'auto_restart': config['auto_restart'],
                    'restart_delay': config['restart_delay']
                }
            }
        
        return status
    
    def get_logs(self, script_name: str, lines: int = 50) -> str:
        """Получение последних строк логов скрипта"""
        try:
            if script_name not in self.running_processes:
                return f"Скрипт {script_name} не запущен"
            
            log_file = Path(self.running_processes[script_name]['log_file'])
            if not log_file.exists():
                return f"Лог файл для {script_name} не найден"
            
            with open(log_file, 'r') as f:
                all_lines = f.readlines()
                last_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
                return ''.join(last_lines)
                
        except Exception as e:
            logger.error(f"Ошибка чтения логов {script_name}: {e}")
            return f"Ошибка чтения логов: {str(e)}"
    
    def cleanup_dead_processes(self):
        """Очистка информации о мертвых процессах"""
        try:
            to_remove = []
            for script_name in self.running_processes:
                if not self.is_process_running(script_name):
                    to_remove.append(script_name)
            
            for script_name in to_remove:
                del self.running_processes[script_name]
                logger.info(f"Удалена информация о мертвом процессе {script_name}")
            
            if to_remove:
                self.save_running_processes()
                
        except Exception as e:
            logger.error(f"Ошибка очистки мертвых процессов: {e}")
    
    def register_existing_process(self, script_name: str, pid: int, user_id: int = None) -> bool:
        """Регистрация уже запущенного процесса"""
        try:
            if script_name not in self.scripts:
                logger.error(f"Скрипт {script_name} не найден в конфигурации")
                return False
            
            # Проверяем, что процесс действительно существует
            try:
                process = psutil.Process(pid)
                if not process.is_running():
                    logger.error(f"Процесс {pid} не запущен")
                    return False
            except psutil.NoSuchProcess:
                logger.error(f"Процесс {pid} не существует")
                return False
            
            script_config = self.scripts[script_name]
            log_file = self.logs_dir / f"{script_name}.log"
            
            # Регистрируем процесс
            self.running_processes[script_name] = {
                'pid': pid,
                'started_at': datetime.now().isoformat(),
                'started_by': user_id,
                'script': script_config['script'],
                'args': script_config['args'],
                'log_file': str(log_file),
                'auto_restart': script_config['auto_restart']
            }
            
            self.save_running_processes()
            logger.info(f"Процесс {script_name} (PID: {pid}) зарегистрирован")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка регистрации процесса {script_name}: {e}")
            return False

    def auto_restart_failed_processes(self):
        """Автоматический перезапуск упавших процессов"""
        try:
            for script_name, config in self.scripts.items():
                if not config['auto_restart']:
                    continue
                
                if not self.is_process_running(script_name):
                    logger.info(f"Автоматический перезапуск {script_name}")
                    self.start_script(script_name)
                    time.sleep(config['restart_delay'])
                    
        except Exception as e:
            logger.error(f"Ошибка автоперезапуска: {e}")

# Глобальный экземпляр менеджера процессов
process_manager = ProcessManager() 