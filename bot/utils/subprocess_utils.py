"""
サブプロセス実行ユーティリティ

クロスプラットフォーム対応の安全なsubprocess実行
"""

import os
import sys
import subprocess
import platform
import logging

logger = logging.getLogger(__name__)

def safe_subprocess_run(*args, **kwargs):
    """
    クロスプラットフォーム対応の安全なsubprocess.run呼び出し
    
    Args:
        *args: subprocess.runに渡す引数
        **kwargs: subprocess.runに渡すキーワード引数
        
    Returns:
        subprocess.CompletedProcess: 実行結果
    """
    try:
        # 環境変数を設定
        env = kwargs.get('env', os.environ.copy())
        env['PYTHONIOENCODING'] = 'utf-8'
        env['PYTHONUTF8'] = '1'
        
        # Windows環境での追加設定
        if platform.system() == 'Windows':
            env['PYTHONLEGACYWINDOWSSTDIO'] = 'utf-8'
            env['PYTHONLEGACYWINDOWSFSENCODING'] = 'utf-8'
            # Windows用のstartupinfo設定
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            kwargs['startupinfo'] = startupinfo
        
        kwargs['env'] = env
        
        # エンコーディング設定を強制
        kwargs['encoding'] = 'utf-8'
        kwargs['errors'] = 'replace'
        
        # capture_outputが設定されている場合は、stdout/stderrを個別に設定しない
        if kwargs.get('capture_output', False):
            # capture_outputがTrueの場合は、stdout/stderrを削除
            kwargs.pop('stdout', None)
            kwargs.pop('stderr', None)
        else:
            # capture_outputがない場合のみ、stdout/stderrを設定
            if 'stdout' not in kwargs:
                kwargs['stdout'] = subprocess.PIPE
            if 'stderr' not in kwargs:
                kwargs['stderr'] = subprocess.PIPE
        
        # Windows環境での追加設定
        if platform.system() == 'Windows':
            # Windowsでは、より安全な設定を使用
            kwargs['text'] = True
            kwargs['universal_newlines'] = True
            kwargs['shell'] = False
        
        # タイムアウトの設定（デフォルト30秒）
        if 'timeout' not in kwargs:
            kwargs['timeout'] = 30
            
        result = subprocess.run(*args, **kwargs)
        logger.debug(f"Subprocess completed with return code: {result.returncode}")
        return result
        
    except subprocess.TimeoutExpired as e:
        logger.warning(f"Subprocess timeout: {e}")
        return subprocess.CompletedProcess(args, returncode=-1, stdout=None, stderr=f"Timeout: {str(e)}")
    except subprocess.CalledProcessError as e:
        logger.warning(f"Subprocess returned non-zero exit status: {e}")
        return subprocess.CompletedProcess(args, returncode=e.returncode, stdout=e.stdout, stderr=e.stderr)
    except FileNotFoundError as e:
        logger.error(f"Command not found: {e}")
        return subprocess.CompletedProcess(args, returncode=-1, stdout=None, stderr=f"Command not found: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected subprocess error: {e}")
        # エラーが発生した場合、適切なエラーオブジェクトを返す
        return subprocess.CompletedProcess(args, returncode=-1, stdout=None, stderr=str(e))

def get_subprocess_env():
    """サブプロセス用の環境変数辞書を取得"""
    env = os.environ.copy()
    env.update({
        'PYTHONIOENCODING': 'utf-8',
        'PYTHONUTF8': '1'
    })
    
    if platform.system() == 'Windows':
        env.update({
            'PYTHONLEGACYWINDOWSSTDIO': 'utf-8',
            'PYTHONLEGACYWINDOWSFSENCODING': 'utf-8'
        })
    
    return env
