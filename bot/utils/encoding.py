"""
エンコーディング処理ユーティリティ

クロスプラットフォーム対応のエンコーディング設定を提供
"""

import os
import sys
import logging
import platform

logger = logging.getLogger(__name__)

def setup_encoding():
    """すべての環境でエンコーディング問題を回避する設定"""
    try:
        # 環境変数を設定
        os.environ['PYTHONIOENCODING'] = 'utf-8'
        os.environ['PYTHONUTF8'] = '1'
        
        # Windows環境での追加設定
        if platform.system() == 'Windows':
            os.environ['PYTHONLEGACYWINDOWSSTDIO'] = 'utf-8'
            os.environ['PYTHONLEGACYWINDOWSFSENCODING'] = 'utf-8'
            # Windowsでのコンソールエンコーディングを設定
            try:
                import codecs
                if hasattr(sys.stdout, 'detach'):
                    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.detach())
                if hasattr(sys.stderr, 'detach'):
                    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.detach())
            except Exception as e:
                logger.warning(f"Failed to setup Windows console encoding: {e}")
        
        # 標準出力と標準エラーのエンコーディングを設定
        if hasattr(sys.stdout, 'reconfigure'):
            try:
                sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            except Exception as e:
                logger.warning(f"Failed to reconfigure stdout: {e}")
        if hasattr(sys.stderr, 'reconfigure'):
            try:
                sys.stderr.reconfigure(encoding='utf-8', errors='replace')
            except Exception as e:
                logger.warning(f"Failed to reconfigure stderr: {e}")
        
        # locale設定をUTF-8に変更（可能な場合）
        try:
            import locale
            if hasattr(locale, 'setlocale'):
                if platform.system() == 'Windows':
                    # WindowsではUTF-8ロケールを試行
                    try:
                        locale.setlocale(locale.LC_ALL, 'C.UTF-8')
                    except Exception:
                        try:
                            locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
                        except Exception:
                            pass
                else:
                    locale.setlocale(locale.LC_ALL, 'C.UTF-8')
        except Exception as e:
            logger.warning(f"Failed to setup locale: {e}")
            
        logger.info("Encoding setup completed successfully")
            
    except Exception as e:
        # エンコーディング設定に失敗しても続行
        logger.warning(f"Encoding setup failed: {e}")

def setup_windows_encoding():
    """Windows環境での追加エンコーディング設定"""
    if os.name != 'nt':  # Windows以外では何もしない
        return
    
    try:
        import codecs
        import locale
        
        # システム全体のエンコーディングをUTF-8に設定
        if hasattr(sys.stdout, 'reconfigure'):
            try:
                sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            except Exception:
                pass
        if hasattr(sys.stderr, 'reconfigure'):
            try:
                sys.stderr.reconfigure(encoding='utf-8', errors='replace')
            except Exception:
                pass
        
        # 環境変数をさらに設定
        os.environ['PYTHONIOENCODING'] = 'utf-8'
        os.environ['PYTHONUTF8'] = '1'
        os.environ['PYTHONLEGACYWINDOWSSTDIO'] = 'utf-8'
        os.environ['PYTHONLEGACYWINDOWSFSENCODING'] = 'utf-8'
        
        # ロケール設定をUTF-8に変更
        try:
            locale.setlocale(locale.LC_ALL, 'C.UTF-8')
        except Exception:
            try:
                locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
            except Exception:
                pass
                
        logger.info("Windows encoding setup completed")
        
    except Exception as e:
        logger.warning(f"Windows encoding setup failed: {e}")

# Windows環境での初期設定を実行
if os.name == 'nt':
    setup_windows_encoding()
