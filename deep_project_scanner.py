import os
import json
import sys
from pathlib import Path
import argparse
from datetime import datetime
import re

def generate_ai_analysis_package(start_path, output_dir="ai_analysis"):
    """
    Tạo gói dữ liệu phân tích đầy đủ cho AI xử lý - TỐI ƯU CHO BACKEND & FRONTEND
    
    Args:
        start_path: Đường dẫn dự án
        output_dir: Thư mục xuất kết quả
    """
    
    start_path = Path(start_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if not start_path.exists():
        print(f"❌ Đường dẫn không tồn tại: {start_path}")
        return None
    
    # Cấu hình loại trừ
    EXCLUDE_DIRS = {'.git', '__pycache__', 'node_modules', '.vscode', '.idea', 
                   'venv', 'env', 'dist', 'build', '.next', '.nuxt', '.expo'}
    EXCLUDE_FILES = {'.DS_Store', 'thumbs.db', '.gitignore', '.env.local', '.env.production'}
    
    # File types cần đọc nội dung - MỞ RỘNG CHO WEB DEV
    CODE_EXTENSIONS = {'.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.c', 
                      '.html', '.css', '.scss', '.less', '.php', '.rb', '.go', '.rs', 
                      '.json', '.xml', '.yaml', '.yml', '.md', '.txt', '.config', 
                      '.conf', '.ini', '.env', '.sql', '.graphql', '.gql', '.vue', '.svelte'}
    
    IGNORE_CONTENT_FILES = {'package-lock.json', 'yarn.lock', '.db', '.sqlite', '.db-journal'}  # File lớn, bỏ qua nội dung
    
    analysis_data = {
        "metadata": {
            "project_path": str(start_path.absolute()),
            "analysis_date": datetime.now().isoformat(),
            "total_files": 0,
            "total_size_bytes": 0,
            "scanned_directories": 0,
            "scanned_files": 0
        },
        "file_tree": [],
        "file_types": {},
        "file_contents": {},
        "project_structure": {},
        "key_files": {},
        "backend_files": {},
        "frontend_files": {},
        "api_endpoints": {},
        "database_files": {},
        "config_files": {}
    }
    
    print(f"🔍 Đang phân tích dự án tại: {start_path}")
    
    def is_high_priority_file(file_path):
        """Kiểm tra file có độ ưu tiên cao không"""
        file_str = str(file_path).lower()
        
        # Backend files
        if any(pattern in file_str for pattern in ['/api/', '/models/', '/schemas/', '/crud/', '/services/', '/routes/', '/controllers/', '/middleware/']):
            return True
        if file_str.endswith(('.py', '.json', '.yaml', '.yml', '.toml')) and any(term in file_str for term in ['backend', 'server', 'api']):
            return True
            
        # Frontend files
        if any(pattern in file_str for pattern in ['/components/', '/features/', '/pages/', '/app/', '/views/', '/screens/', '/layouts/']):
            return True
        if file_str.endswith(('.tsx', '.ts', '.jsx', '.js', '.vue', '.svelte')) and any(term in file_str for term in ['frontend', 'client', 'app']):
            return True
            
        # Config files
        config_names = ['package.json', 'requirements.txt', 'dockerfile', 'docker-compose', 
                       'webpack.config', 'vite.config', 'next.config', 'nuxt.config',
                       'tailwind.config', 'postcss.config', 'tsconfig.json', 'babel.config',
                       '.env', 'config.py', 'settings.py', 'app.py', 'main.py']
        if any(name in file_str for name in config_names):
            return True
            
        return False
    
    def scan_directory(current_path, relative_path="", depth=0):
        """Quét đệ quy thư mục - TỐI ƯU CHO BACKEND/FRONTEND"""
        try:
            if relative_path:
                analysis_data["metadata"]["scanned_directories"] += 1
            
            items = []
            for item in current_path.iterdir():
                if item.name in EXCLUDE_DIRS and item.is_dir():
                    continue
                if item.name in EXCLUDE_FILES and item.is_file():
                    continue
                items.append(item)
            
            items.sort(key=lambda x: (not x.is_dir(), x.name.lower()))
            
            for item in items:
                item_rel_path = relative_path + "/" + item.name if relative_path else item.name
                
                if item.is_dir():
                    # Thư mục
                    analysis_data["file_tree"].append({
                        "type": "directory",
                        "name": item.name,
                        "path": str(item_rel_path),
                        "depth": depth
                    })
                    
                    # Thêm vào project structure
                    if depth <= 3:  # Tăng lên 3 level để capture backend/app/api
                        analysis_data["project_structure"][str(item_rel_path)] = {
                            "type": "directory",
                            "path": str(item_rel_path)
                        }
                    
                    # Đệ quy vào thư mục con
                    scan_directory(item, item_rel_path, depth + 1)
                    
                else:
                    # File
                    analysis_data["metadata"]["scanned_files"] += 1
                    try:
                        file_size = item.stat().st_size
                        analysis_data["metadata"]["total_files"] += 1
                        analysis_data["metadata"]["total_size_bytes"] += file_size
                        
                        # Phân loại file
                        ext = item.suffix.lower()
                        if ext:
                            analysis_data["file_types"][ext] = analysis_data["file_types"].get(ext, 0) + 1
                        else:
                            analysis_data["file_types"]['[no_extension]'] = analysis_data["file_types"].get('[no_extension]', 0) + 1
                        
                        # Thêm vào file tree
                        tree_item = {
                            "type": "file",
                            "name": item.name,
                            "path": str(item_rel_path),
                            "size_bytes": file_size,
                            "size_human": format_size(file_size),
                            "extension": ext,
                            "depth": depth
                        }
                        analysis_data["file_tree"].append(tree_item)
                        
                        # PHÂN LOẠI FILE THEO LOẠI
                        file_path_str = str(item_rel_path).lower()
                        
                        # Backend files
                        if any(term in file_path_str for term in ['backend', 'server', 'api', 'models', 'schemas', 'database']):
                            if ext in ['.py', '.java', '.go', '.rb', '.php']:
                                analysis_data["backend_files"][str(item_rel_path)] = {
                                    "size": file_size,
                                    "type": ext,
                                    "category": get_file_category(file_path_str, ext)
                                }
                        
                        # Frontend files
                        if any(term in file_path_str for term in ['frontend', 'client', 'app', 'components', 'pages', 'views']):
                            if ext in ['.js', '.jsx', '.ts', '.tsx', '.vue', '.svelte', '.html', '.css']:
                                analysis_data["frontend_files"][str(item_rel_path)] = {
                                    "size": file_size,
                                    "type": ext,
                                    "category": get_file_category(file_path_str, ext)
                                }
                        
                        # Database files
                        if ext in ['.sql', '.sqlite', '.db', '.mdb']:
                            analysis_data["database_files"][str(item_rel_path)] = {
                                "size": file_size,
                                "type": ext
                            }
                        
                        # Config files
                        config_names = ['package.json', 'dockerfile', 'docker-compose', 'webpack.config', 
                                       'vite.config', 'next.config', 'tailwind.config', 'tsconfig.json',
                                       'requirements.txt', 'pyproject.toml', 'composer.json', 'pom.xml']
                        if any(name in item.name.lower() for name in config_names):
                            analysis_data["config_files"][str(item_rel_path)] = {
                                "size": file_size,
                                "type": ext
                            }
                        
                        # Đọc nội dung file quan trọng
                        should_read_content = (
                            (ext in CODE_EXTENSIONS and 
                             item.name not in IGNORE_CONTENT_FILES) or
                            is_high_priority_file(file_path_str)
                        )
                        
                        # Điều chỉnh kích thước file dựa trên loại
                        max_size = 50000  # 50KB mặc định
                        if ext in ['.json', '.py', '.js', '.ts']:
                            max_size = 100000  # 100KB cho code files
                        elif ext in ['.md', '.txt']:
                            max_size = 50000  # 50KB cho text files
                        
                        if should_read_content and file_size < max_size:
                            try:
                                # Thử nhiều encoding
                                content = None
                                encoding_used = 'utf-8'
                                encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252', 'utf-16']
                                for enc in encodings:
                                    try:
                                        with open(item, 'r', encoding=enc) as f:
                                            content = f.read()
                                        encoding_used = enc
                                        break
                                    except (UnicodeDecodeError, UnicodeError):
                                        continue
                                
                                if content is not None:
                                    content_preview = content[:15000]  # Giới hạn 15k ký tự
                                    analysis_data["file_contents"][str(item_rel_path)] = {
                                        "size": file_size,
                                        "lines": len(content.splitlines()),
                                        "content": content_preview,
                                        "encoding": encoding_used
                                    }
                                    
                                    # PHÂN TÍCH API ENDPOINTS
                                    if '/api/' in file_path_str and file_path_str.endswith(('.py', '.js', '.ts')):
                                        extract_api_endpoints(str(item_rel_path), content_preview)
                                    
                                    # PHÂN TÍCH DATABASE SCHEMA
                                    if any(term in file_path_str for term in ['models.', 'schema.', 'migration.']):
                                        extract_database_info(str(item_rel_path), content_preview)
                                
                                # Đánh dấu file quan trọng
                                if is_key_file(item.name, ext, file_path_str):
                                    priority = "high" if is_high_priority_file(file_path_str) else "normal"
                                    analysis_data["key_files"][str(item_rel_path)] = {
                                        "type": get_file_type(item.name, ext),
                                        "category": get_file_category(file_path_str, ext),
                                        "description": get_file_description(item.name, ext, file_path_str),
                                        "priority": priority
                                    }
                                    
                            except (UnicodeDecodeError, PermissionError, OSError, Exception) as e:
                                analysis_data["file_contents"][str(item_rel_path)] = {
                                    "error": f"Cannot read file: {str(e)[:100]}",
                                    "size": file_size
                                }
                                
                    except (OSError, PermissionError) as e:
                        print(f"⚠️ Lỗi đọc file {item_rel_path}: {e}")
                        continue
                        
        except PermissionError as e:
            print(f"⚠️ Không có quyền truy cập thư mục: {relative_path}")
        except Exception as e:
            print(f"⚠️ Lỗi khi quét thư mục {relative_path}: {e}")
    
    def get_file_category(file_path, extension):
        """Xác định category của file"""
        file_path_lower = file_path.lower()
        
        if '/api/' in file_path_lower or '/routes/' in file_path_lower:
            return 'api'
        elif '/models/' in file_path_lower or '/schemas/' in file_path_lower:
            return 'database'
        elif '/components/' in file_path_lower:
            return 'ui_components'
        elif '/pages/' in file_path_lower or '/app/' in file_path_lower:
            return 'pages'
        elif '/services/' in file_path_lower:
            return 'services'
        elif '/utils/' in file_path_lower or '/lib/' in file_path_lower:
            return 'utilities'
        elif '/config/' in file_path_lower:
            return 'configuration'
        elif '/tests/' in file_path_lower:
            return 'testing'
        elif '/docs/' in file_path_lower:
            return 'documentation'
        elif extension in ['.css', '.scss', '.less', '.sass']:
            return 'styling'
        elif extension in ['.js', '.jsx', '.ts', '.tsx']:
            return 'frontend_code'
        elif extension == '.py':
            return 'backend_code'
        else:
            return 'other'
    
    def extract_api_endpoints(file_path, content):
        """Trích xuất thông tin API endpoints từ file"""
        endpoints = []
        lines = content.split('\n')
        
        for i, line in enumerate(lines):
            line = line.strip()
            
            # Python FastAPI/FastAPI/Flask
            if any(dec in line for dec in ['@router.', '@app.', '@blueprint.']):
                endpoint_info = {
                    "file": file_path,
                    "line": i + 1,
                    "method": extract_http_method(line),
                    "path": extract_path(line),
                    "function": extract_function_name(lines, i)
                }
                endpoints.append(endpoint_info)
            
            # Express.js/Node.js
            elif any(dec in line for dec in ['router.get', 'router.post', 'router.put', 'router.delete', 
                                            'app.get', 'app.post', 'app.put', 'app.delete']):
                endpoint_info = {
                    "file": file_path,
                    "line": i + 1,
                    "method": extract_http_method_js(line),
                    "path": extract_path_js(line),
                    "function": extract_function_name_js(lines, i)
                }
                endpoints.append(endpoint_info)
        
        if endpoints:
            analysis_data["api_endpoints"][file_path] = endpoints
    
    def extract_http_method(line):
        """Trích xuất HTTP method từ decorator Python"""
        if '@router.get' in line or '@app.get' in line: return 'GET'
        if '@router.post' in line or '@app.post' in line: return 'POST'
        if '@router.put' in line or '@app.put' in line: return 'PUT'
        if '@router.delete' in line or '@app.delete' in line: return 'DELETE'
        if '@router.patch' in line or '@app.patch' in line: return 'PATCH'
        return 'UNKNOWN'
    
    def extract_http_method_js(line):
        """Trích xuất HTTP method từ JavaScript/TypeScript"""
        if '.get(' in line: return 'GET'
        if '.post(' in line: return 'POST'
        if '.put(' in line: return 'PUT'
        if '.delete(' in line: return 'DELETE'
        if '.patch(' in line: return 'PATCH'
        return 'UNKNOWN'
    
    def extract_path(line):
        """Trích xuất path từ decorator Python"""
        # Tìm path trong quotes
        matches = re.findall(r'["\']([^"\']+)["\']', line)
        if matches and len(matches) > 0:
            return matches[0]
        return 'UNKNOWN'
    
    def extract_path_js(line):
        """Trích xuất path từ JavaScript"""
        matches = re.findall(r'["\']([^"\']+)["\']', line)
        if matches and len(matches) > 0:
            return matches[0]
        return 'UNKNOWN'
    
    def extract_function_name(lines, start_index):
        """Trích xuất tên function từ decorator Python"""
        for i in range(start_index + 1, min(start_index + 5, len(lines))):
            if 'def ' in lines[i]:
                match = lines[i].strip().split('def ')[1].split('(')[0].strip()
                return match
        return 'UNKNOWN'
    
    def extract_function_name_js(lines, start_index):
        """Trích xuất tên function từ JavaScript"""
        for i in range(start_index, min(start_index + 3, len(lines))):
            if 'function' in lines[i]:
                # function myFunction() hoặc const myFunction = () => 
                line = lines[i].strip()
                if 'function ' in line:
                    parts = line.split('function ')
                    if len(parts) > 1:
                        return parts[1].split('(')[0].strip()
                elif 'const ' in line or 'let ' in line or 'var ' in line:
                    parts = line.split('=')
                    if len(parts) > 0:
                        func_name = parts[0].replace('const', '').replace('let', '').replace('var', '').strip()
                        return func_name
        return 'UNKNOWN'
    
    def extract_database_info(file_path, content):
        """Trích xuất thông tin database từ file"""
        # Có thể thêm logic extract models, schemas ở đây
        pass
    
    def is_key_file(filename, extension, file_path):
        """Xác định file quan trọng"""
        file_path_lower = file_path.lower()
        
        # File cấu hình quan trọng
        config_files = {
            'package.json', 'requirements.txt', 'dockerfile', 'docker-compose.yml',
            'docker-compose.yaml', 'readme.md', 'makefile', '.gitignore', 
            'env.example', '.env', 'config.json', 'settings.py', 'app.py', 
            'main.py', 'index.js', 'server.js', 'webpack.config.js', 
            'tsconfig.json', 'pom.xml', 'build.gradle', 'next.config.js', 
            'vite.config.js', 'tailwind.config.js', 'layout.tsx', 'page.tsx', 
            '_app.tsx', '_document.tsx', 'config.py', 'models.py', 'schemas.py', 
            'crud.py', 'auth.py', 'products.py', 'users.py', 'categories.py',
            'database.py', 'ormconfig.json', '.env.example', 'pyproject.toml',
            'compose.yml', 'nginx.conf', 'docker-compose.prod.yml'
        }
        
        # Ưu tiên file trong các thư mục quan trọng
        important_dirs = ['/backend/', '/frontend/', '/app/', '/api/', '/src/']
        if any(dir_name in file_path_lower for dir_name in important_dirs):
            if extension in ['.py', '.js', '.ts', '.jsx', '.tsx', '.json', '.yaml', '.yml']:
                return True
        
        return filename.lower() in config_files
    
    def get_file_type(filename, extension):
        """Xác định loại file"""
        config_files = {'.json', '.yaml', '.yml', '.config', '.conf', '.ini', '.toml'}
        code_files = {'.py', '.js', '.ts', '.java', '.cpp', '.c', '.php', '.rb', '.go', '.rs'}
        web_files = {'.html', '.htm', '.css', '.scss', '.less', '.jsx', '.tsx', '.vue', '.svelte'}
        style_files = {'.css', '.scss', '.less', '.sass'}
        data_files = {'.sql', '.csv', '.xml', '.jsonl'}
        
        if extension in config_files:
            return "config"
        elif extension in code_files:
            return "code"
        elif extension in web_files:
            return "web"
        elif extension in style_files:
            return "style"
        elif extension in data_files:
            return "data"
        elif extension == '.md':
            return "documentation"
        elif extension in ['.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp']:
            return "image"
        else:
            return "other"
    
    def get_file_description(filename, extension, file_path):
        """Mô tả file"""
        descriptions = {
            'package.json': 'Node.js project configuration and dependencies',
            'requirements.txt': 'Python dependencies list',
            'pyproject.toml': 'Python project configuration (PEP 621)',
            'dockerfile': 'Docker container configuration',
            'docker-compose.yml': 'Docker Compose configuration',
            'readme.md': 'Project documentation',
            '.gitignore': 'Git ignore rules',
            'main.py': 'Python main application file',
            'app.py': 'Python application file',
            'index.js': 'JavaScript main file',
            'server.js': 'Node.js server file',
            'layout.tsx': 'Next.js layout component',
            'page.tsx': 'Next.js page component',
            'config.py': 'Application configuration',
            'models.py': 'Database models',
            'schemas.py': 'Pydantic schemas',
            'crud.py': 'CRUD operations',
            'auth.py': 'Authentication endpoints',
            'products.py': 'Product management endpoints',
            'users.py': 'User management endpoints',
            'categories.py': 'Category management',
            'database.py': 'Database configuration',
            'settings.py': 'Django settings',
            'urls.py': 'Django URL routing',
            'views.py': 'Django views',
            'manage.py': 'Django management script',
            '.env': 'Environment variables',
            '.env.example': 'Environment variables template',
            'tsconfig.json': 'TypeScript configuration',
            'next.config.js': 'Next.js configuration',
            'vite.config.js': 'Vite configuration',
            'tailwind.config.js': 'Tailwind CSS configuration',
            'postcss.config.js': 'PostCSS configuration',
            'webpack.config.js': 'Webpack configuration',
            'babel.config.js': 'Babel configuration'
        }
        
        # Mô tả dựa trên đường dẫn
        file_path_lower = file_path.lower()
        
        if '/api/' in file_path_lower:
            return f"API endpoints - {filename}"
        elif '/models/' in file_path_lower or '/schemas/' in file_path_lower:
            return f"Database models/schemas - {filename}"
        elif '/components/' in file_path_lower:
            return f"React component - {filename}"
        elif '/pages/' in file_path_lower:
            return f"Page component - {filename}"
        elif '/features/' in file_path_lower:
            return f"Feature module - {filename}"
        elif '/services/' in file_path_lower:
            return f"Service layer - {filename}"
        elif '/utils/' in file_path_lower or '/lib/' in file_path_lower:
            return f"Utility functions - {filename}"
        elif '/tests/' in file_path_lower or '/test/' in file_path_lower:
            return f"Test file - {filename}"
        elif '/docs/' in file_path_lower or '/documentation/' in file_path_lower:
            return f"Documentation - {filename}"
        elif '/migrations/' in file_path_lower:
            return f"Database migration - {filename}"
        elif '/seeders/' in file_path_lower or '/seeds/' in file_path_lower:
            return f"Database seeder - {filename}"
        
        return descriptions.get(filename.lower(), f"{extension} file - {filename}")
    
    def format_size(size_bytes):
        """Định dạng kích thước"""
        if size_bytes == 0:
            return "0 B"
        
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
    
    # Bắt đầu quét
    print(f"📁 Quét dự án: {start_path}")
    print(f"📊 Output: {output_dir}")
    print("⏳ Đang phân tích...")
    
    scan_directory(start_path)
    
    # Tạo file đầu ra với tên cố định (chỉ 3 file duy nhất, ghi đè mỗi lần chạy)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 1. File JSON đầy đủ
    json_file = output_dir / "project_analysis.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(analysis_data, f, indent=2, ensure_ascii=False)
    
    # 2. File tree text
    tree_file = output_dir / "project_tree.txt"
    with open(tree_file, 'w', encoding='utf-8') as f:
        f.write(generate_text_tree(analysis_data))
    
    # 3. File summary cho AI
    summary_file = output_dir / "ai_summary.md"
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write(generate_ai_summary(analysis_data))
    
    print(f"\n✅ ĐÃ TẠO GÓI PHÂN TÍCH BACKEND & FRONTEND (3 FILE DUY NHẤT):")
    print(f"   📊 project_analysis.json - Dữ liệu đầy đủ (JSON)")
    print(f"   🌳 project_tree.txt - Cây thư mục (Text)")
    print(f"   🤖 ai_summary.md - Tóm tắt cho AI (Markdown)")
    print(f"   📁 Backend files: {len(analysis_data['backend_files'])}")
    print(f"   📱 Frontend files: {len(analysis_data['frontend_files'])}")
    print(f"   ⚙️ Config files: {len(analysis_data['config_files'])}")
    print(f"   🗃️ Database files: {len(analysis_data['database_files'])}")
    print(f"   🔗 API endpoints: {sum(len(v) for v in analysis_data['api_endpoints'].values())}")
    print(f"   📝 Files with content: {len(analysis_data['file_contents'])}")
    print(f"\n📁 Tất cả files được lưu tại: {output_dir.absolute()}")
    
    return {
        "json_file": json_file,
        "tree_file": tree_file,
        "summary_file": summary_file,
        "analysis_data": analysis_data
    }

def generate_text_tree(analysis_data):
    """Tạo cây thư mục dạng text"""
    lines = [f"# PROJECT TREE ANALYSIS", ""]
    lines.append(f"Project: {analysis_data['metadata']['project_path']}")
    lines.append(f"Date: {analysis_data['metadata']['analysis_date']}")
    lines.append(f"Total Files: {analysis_data['metadata']['total_files']}")
    lines.append(f"Total Size: {format_size(analysis_data['metadata']['total_size_bytes'])}")
    lines.append(f"Scanned Directories: {analysis_data['metadata']['scanned_directories']}")
    lines.append(f"Scanned Files: {analysis_data['metadata']['scanned_files']}")
    lines.append("")
    lines.append("## FILE TREE")
    lines.append("")
    
    # Sắp xếp file tree theo depth và name
    sorted_tree = sorted(analysis_data["file_tree"], key=lambda x: (x["depth"], x["name"]))
    
    for item in sorted_tree:
        indent = "    " * item["depth"]
        if item["type"] == "directory":
            # Đếm số file trong thư mục
            dir_files = [f for f in analysis_data["file_tree"] 
                        if f["type"] == "file" and f["path"].startswith(item["path"] + "/")]
            count_text = f" ({len(dir_files)} files)" if dir_files else ""
            lines.append(f"{indent}📁 {item['name']}/{count_text}")
        else:
            # Xác định icon dựa trên loại file
            icon = get_file_icon(item['name'], item['extension'], item['path'])
            size_text = f" ({item['size_human']})" if 'size_human' in item else ""
            lines.append(f"{indent}{icon} {item['name']}{size_text}")
    
    lines.append("")
    lines.append("## FILE TYPE STATISTICS")
    for ext, count in sorted(analysis_data["file_types"].items(), key=lambda x: x[1], reverse=True):
        if analysis_data["metadata"]["total_files"] > 0:
            percentage = (count / analysis_data["metadata"]["total_files"]) * 100
            lines.append(f"- {ext}: {count} files ({percentage:.1f}%)")
        else:
            lines.append(f"- {ext}: {count} files")
    
    # Thêm thông tin backend/frontend
    lines.append("")
    lines.append("## PROJECT BREAKDOWN")
    lines.append(f"- Backend files: {len(analysis_data['backend_files'])}")
    lines.append(f"- Frontend files: {len(analysis_data['frontend_files'])}")
    lines.append(f"- Config files: {len(analysis_data['config_files'])}")
    lines.append(f"- Database files: {len(analysis_data['database_files'])}")
    
    return "\n".join(lines)

def get_file_icon(filename, extension, file_path):
    """Xác định icon cho file dựa trên loại"""
    file_path_lower = file_path.lower()
    
    # Backend icons
    if extension == '.py':
        return '🐍'
    elif extension in ['.js', '.jsx']:
        if 'backend' in file_path_lower or 'server' in file_path_lower:
            return '🟨'
        return '📄'
    elif extension in ['.ts', '.tsx']:
        return '📘'
    elif extension in ['.java', '.cpp', '.c']:
        return '☕'
    elif extension == '.go':
        return '🐹'
    elif extension == '.rs':
        return '🦀'
    elif extension == '.php':
        return '🐘'
    
    # Frontend icons
    elif extension in ['.html', '.htm']:
        return '🌐'
    elif extension in ['.css', '.scss', '.less', '.sass']:
        return '🎨'
    elif extension in ['.vue', '.svelte']:
        return '⚡'
    
    # Data & Config icons
    elif extension == '.json':
        return '📋'
    elif extension in ['.yaml', '.yml']:
        return '⚙️'
    elif extension == '.sql':
        return '🗃️'
    elif extension in ['.md', '.txt']:
        return '📝'
    elif extension in ['.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp']:
        return '🖼️'
    
    # Special files
    elif filename.lower() == 'dockerfile':
        return '🐳'
    elif 'docker-compose' in filename.lower():
        return '🐳'
    elif filename.lower() == 'package.json':
        return '📦'
    elif filename.lower() == 'requirements.txt':
        return '📋'
    elif filename.lower() == '.gitignore':
        return '👁️'
    elif filename.lower() in ['readme.md', 'readme.txt']:
        return '📖'
    elif filename.lower() == '.env':
        return '🔐'
    
    return '📄'

def generate_ai_summary(analysis_data):
    """Tạo tóm tắt cho AI"""
    lines = ["# AI ANALYSIS SUMMARY", ""]
    
    lines.append("## PROJECT OVERVIEW")
    lines.append(f"- **Path**: `{analysis_data['metadata']['project_path']}`")
    lines.append(f"- **Total Files**: {analysis_data['metadata']['total_files']}")
    lines.append(f"- **Total Size**: {format_size(analysis_data['metadata']['total_size_bytes'])}")
    lines.append(f"- **Scanned Directories**: {analysis_data['metadata']['scanned_directories']}")
    lines.append(f"- **Scanned Files**: {analysis_data['metadata']['scanned_files']}")
    lines.append("")
    
    lines.append("## PROJECT STRUCTURE")
    # Lấy top-level directories
    top_dirs = [path for path, info in analysis_data["project_structure"].items() 
                if info['type'] == 'directory' and path.count('/') == 0]
    
    for dir_name in sorted(top_dirs)[:20]:
        # Đếm file types trong thư mục
        dir_files = [f for f in analysis_data["file_tree"] 
                    if f["type"] == "file" and f["path"].startswith(dir_name + "/")]
        
        if dir_files:
            file_types = {}
            for f in dir_files:
                ext = f.get('extension', '[no_extension]')
                file_types[ext] = file_types.get(ext, 0) + 1
            
            type_summary = ", ".join([f"{k}:{v}" for k, v in list(file_types.items())[:3]])
            lines.append(f"- `{dir_name}/` - {len(dir_files)} files ({type_summary})")
        else:
            lines.append(f"- `{dir_name}/`")
    lines.append("")
    
    lines.append("## KEY FILES IDENTIFIED")
    high_priority_files = [(path, info) for path, info in analysis_data["key_files"].items() 
                          if info.get('priority') == 'high']
    normal_priority_files = [(path, info) for path, info in analysis_data["key_files"].items() 
                           if info.get('priority') != 'high']
    
    if high_priority_files:
        lines.append("### 🔴 HIGH PRIORITY")
        for path, info in high_priority_files[:15]:
            lines.append(f"- `{path}` - **{info['type']}** - {info['description']}")
    
    if normal_priority_files:
        lines.append("")
        lines.append("### 🟡 NORMAL PRIORITY")
        for path, info in normal_priority_files[:10]:
            lines.append(f"- `{path}` - {info['type']} - {info['description']}")
    lines.append("")
    
    lines.append("## FILE TYPE DISTRIBUTION (Top 15)")
    sorted_types = sorted(analysis_data["file_types"].items(), key=lambda x: x[1], reverse=True)[:15]
    for ext, count in sorted_types:
        if analysis_data["metadata"]["total_files"] > 0:
            percentage = (count / analysis_data["metadata"]["total_files"]) * 100
            lines.append(f"- `{ext}`: {count} files ({percentage:.1f}%)")
    lines.append("")
    
    lines.append("## BACKEND/FONTEND ANALYSIS")
    lines.append("### Backend Files")
    backend_by_type = {}
    for path, info in analysis_data["backend_files"].items():
        file_type = info.get('type', 'unknown')
        backend_by_type[file_type] = backend_by_type.get(file_type, 0) + 1
    
    for file_type, count in sorted(backend_by_type.items(), key=lambda x: x[1], reverse=True)[:10]:
        lines.append(f"- `{file_type}`: {count} files")
    
    lines.append("")
    lines.append("### Frontend Files")
    frontend_by_type = {}
    for path, info in analysis_data["frontend_files"].items():
        file_type = info.get('type', 'unknown')
        frontend_by_type[file_type] = frontend_by_type.get(file_type, 0) + 1
    
    for file_type, count in sorted(frontend_by_type.items(), key=lambda x: x[1], reverse=True)[:10]:
        lines.append(f"- `{file_type}`: {count} files")
    lines.append("")
    
    lines.append("## API ENDPOINTS FOUND")
    total_endpoints = 0
    for file_path, endpoints in analysis_data["api_endpoints"].items():
        lines.append(f"### `{file_path}`")
        lines.append(f"**{len(endpoints)} endpoints**")
        total_endpoints += len(endpoints)
        for endpoint in endpoints[:5]:  # Hiển thị 5 endpoints đầu tiên mỗi file
            lines.append(f"- `{endpoint['method']}` `{endpoint['path']}` → `{endpoint['function']}` (line {endpoint['line']})")
        if len(endpoints) > 5:
            lines.append(f"- ... and {len(endpoints) - 5} more endpoints")
        lines.append("")
    
    if total_endpoints == 0:
        lines.append("*No API endpoints detected*")
    else:
        lines.append(f"**Total API Endpoints**: {total_endpoints}")
    lines.append("")
    
    lines.append("## AVAILABLE FILE CONTENTS")
    content_files = [(path, info) for path, info in analysis_data["file_contents"].items() 
                    if "content" in info and "error" not in info]
    
    if content_files:
        lines.append(f"**{len(content_files)} files with readable content:**")
        # Nhóm theo loại file
        files_by_type = {}
        for path, info in content_files:
            ext = Path(path).suffix.lower()
            if ext not in files_by_type:
                files_by_type[ext] = []
            files_by_type[ext].append((path, info))
        
        for ext, files in sorted(files_by_type.items()):
            lines.append(f"\n### `{ext}` files ({len(files)})")
            for path, info in files[:10]:  # 10 files mỗi loại
                lines.append(f"- `{path}` ({info.get('lines', 0)} lines, {info.get('size', 0)} bytes)")
            if len(files) > 10:
                lines.append(f"- ... and {len(files) - 10} more")
    else:
        lines.append("*No file contents available*")
    
    return "\n".join(lines)

def format_size(size_bytes):
    """Định dạng kích thước"""
    if size_bytes == 0:
        return "0 B"
    
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"

def get_smart_default_path():
    """Xác định đường dẫn mặc định thông minh"""
    # 1. Thư mục hiện tại
    current_dir = Path.cwd()
    
    # 2. Kiểm tra nếu có dấu hiệu của dự án
    project_indicators = [
        '.git', 'package.json', 'requirements.txt', 'pyproject.toml',
        'dockerfile', 'docker-compose.yml', 'manage.py', 'app.py',
        'index.js', 'server.js', 'next.config.js', 'vite.config.js'
    ]
    
    for indicator in project_indicators:
        if (current_dir / indicator).exists():
            print(f"✅ Tìm thấy dự án tại thư mục hiện tại (có {indicator})")
            return current_dir
    
    # 3. Thử tìm trong thư mục cha
    parent_dir = current_dir.parent
    for indicator in project_indicators:
        if (parent_dir / indicator).exists():
            print(f"✅ Tìm thấy dự án tại thư mục cha (có {indicator})")
            return parent_dir
    
    # 4. Trả về thư mục hiện tại nếu không tìm thấy gì
    print(f"ℹ️ Sử dụng thư mục hiện tại: {current_dir}")
    return current_dir

def main():
    parser = argparse.ArgumentParser(
        description='Tạo gói phân tích dự án cho AI - TỐI ƯU BACKEND/FRONTEND',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\nVÍ DỤ:
  %(prog)s .                    # Phân tích thư mục hiện tại
  %(prog)s /path/to/project     # Phân tích đường dẫn cụ thể
  %(prog)s -o my_analysis       # Xuất kết quả vào thư mục my_analysis
  %(prog)s . -o ./results       # Phân tích và xuất vào ./results
        """
    )
    
    parser.add_argument('path', nargs='?', default=None, 
                       help='Đường dẫn dự án (mặc định: thư mục hiện tại)')
    parser.add_argument('-o', '--output', default='ai_analysis', 
                       help='Thư mục xuất kết quả (mặc định: ai_analysis)')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Hiển thị thông tin chi tiết khi quét')
    
    args = parser.parse_args()
    
    print("🚀 TẠO GÓI PHÂN TÍCH DỰ ÁN BACKEND & FRONTEND CHO AI")
    print("=" * 60)
    
    # Xác định đường dẫn dự án
    if args.path is None:
        project_path = get_smart_default_path()
    else:
        project_path = Path(args.path)
    
    # Kiểm tra đường dẫn
    if not project_path.exists():
        print(f"❌ Đường dẫn không tồn tại: {project_path}")
        print(f"📌 Đường dẫn hiện tại: {Path.cwd()}")
        print(f"📌 Hãy thử: python {sys.argv[0]} .")
        return
    
    if not project_path.is_dir():
        print(f"❌ Đây không phải thư mục: {project_path}")
        return
    
    print(f"📂 Dự án: {project_path.absolute()}")
    print(f"📁 Output: {args.output}")
    print("🐍 Ưu tiên đọc Backend (Python) & Frontend (React/TypeScript)")
    print("=" * 60)
    
    result = generate_ai_analysis_package(project_path, args.output)
    
    if result:
        print("\n📤 GỬI CHO AI: Chỉ cần gửi 3 file sau:")
        print("1. ai_summary.md - Tổng quan dự án")
        print("2. project_analysis.json - Dữ liệu chi tiết (nếu AI cần)")
        print("3. project_tree.txt - Cấu trúc cây thư mục")
        print(f"\n📁 Files được lưu tại: {args.output}")
        print("   (Mỗi lần chạy sẽ ghi đè files cũ)")
    else:
        print("\n❌ Không thể tạo gói phân tích. Vui lòng kiểm tra đường dẫn.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️ Đã dừng bởi người dùng.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Lỗi không mong muốn: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)