import os
import json
from pathlib import Path
import argparse
from datetime import datetime
import sys
import re

def format_size(size_bytes):
    """Định dạng kích thước"""
    if size_bytes == 0:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"

def generate_ai_analysis_package(start_path, output_dir="ai_analysis"):
    """
    Tạo gói dữ liệu phân tích đầy đủ cho AI xử lý - TỐI ƯU CHO BACKEND & FRONTEND
    
    Args:
        start_path: Đường dẫn dự án
        output_dir: Thư mục xuất kết quả
    """
    
    start_path = Path(start_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)
    
    if not start_path.exists():
        print(f"❌ Đường dẫn không tồn tại: {start_path}")
        return
    
    # Cấu hình loại trừ
    EXCLUDE_DIRS = {'.git', '__pycache__', 'node_modules', '.vscode', '.idea', 
                   'venv', 'env', 'dist', 'build', '.next', '.nuxt', '.terraform',
                   '.serverless', '.cache', 'coverage', '.nyc_output', 'logs'}
    EXCLUDE_FILES = {'.DS_Store', 'thumbs.db', '.gitignore', '.env', '.env.local', 
                    '.env.production', '.env.development', '*.log', '*.tmp', '*.temp'}
    
    # File types cần đọc nội dung - MỞ RỘNG CHO WEB DEV
    CODE_EXTENSIONS = {'.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.c', 
                      '.html', '.css', '.scss', '.less', '.php', '.rb', '.go', '.rs', 
                      '.json', '.xml', '.yaml', '.yml', '.md', '.txt', '.config', 
                      '.conf', '.ini', '.env.example', '.sql', '.graphql', '.gql',
                      '.vue', '.svelte', '.astro', '.dart', '.swift', '.kt', '.kts'}
    
    IGNORE_CONTENT_FILES = {'package-lock.json', 'yarn.lock', '.db', '.sqlite', 
                           '.db-journal', '*.min.js', '*.min.css', '*.map', '*.ico'}
    
    analysis_data = {
        "metadata": {
            "project_path": str(start_path.absolute()),
            "analysis_date": datetime.now().isoformat(),
            "total_files": 0,
            "total_size_bytes": 0,
            "scan_mode": "full_project_scan"
        },
        "file_tree": [],
        "file_types": {},
        "file_contents": {},
        "project_structure": {},
        "key_files": {},
        "backend_files": {},
        "frontend_files": {},
        "api_endpoints": {},
        "config_files": {},
        "build_files": {}
    }
    
    print(f"🔍 Đang phân tích dự án tại: {start_path}")
    
    def should_exclude(path):
        """Kiểm tra xem có nên loại trừ path không"""
        path_str = str(path)
        
        # Kiểm tra tên thư mục
        for exclude_dir in EXCLUDE_DIRS:
            if f"/{exclude_dir}/" in f"/{path_str}/" or path_str.endswith(f"/{exclude_dir}"):
                return True
        
        # Kiểm tra tên file
        for exclude_file in EXCLUDE_FILES:
            if exclude_file.startswith('*'):
                pattern = exclude_file[1:]  # Bỏ dấu *
                if path_str.endswith(pattern):
                    return True
            elif path_str.endswith(exclude_file):
                return True
        
        # Kiểm tra các pattern thông thường
        bad_patterns = ['.git/', 'node_modules/', '__pycache__/', '.idea/', '.vscode/']
        for pattern in bad_patterns:
            if pattern in path_str:
                return True
        
        return False
    
    def is_high_priority_file(file_path):
        """Kiểm tra file có độ ưu tiên cao không"""
        file_str = str(file_path).lower()
        
        # Backend files patterns
        backend_patterns = [
            '/api/', '/routes/', '/controllers/', '/models/', '/schemas/', 
            '/crud/', '/services/', '/utils/', '/middleware/', '/config/',
            '/app/', '/src/', '/lib/', '/server/', '/backend/', '/database/'
        ]
        
        # Frontend files patterns
        frontend_patterns = [
            '/components/', '/features/', '/pages/', '/views/', '/layouts/',
            '/hooks/', '/contexts/', '/store/', '/redux/', '/frontend/',
            '/public/', '/static/', '/assets/', '/styles/', '/theme/'
        ]
        
        # Check if it's a backend or frontend file
        if any(pattern in file_str for pattern in backend_patterns):
            return True
        if any(pattern in file_str for pattern in frontend_patterns):
            return True
            
        # Check file extensions for important files
        if file_str.endswith(('.py', '.js', '.ts', '.jsx', '.tsx', '.json', '.yaml', '.yml')):
            return True
            
        return False
    
    def scan_directory(current_path, relative_path="", depth=0):
        """Quét đệ quy thư mục"""
        try:
            items = []
            for item in current_path.iterdir():
                try:
                    # Bỏ qua nếu trong danh sách loại trừ
                    if should_exclude(item):
                        continue
                    items.append(item)
                except (PermissionError, OSError):
                    continue
            
            items.sort(key=lambda x: (not x.is_dir(), x.name.lower()))
            
            for item in items:
                try:
                    item_rel_path = relative_path + "/" + item.name if relative_path else item.name
                    
                    if should_exclude(item):
                        continue
                        
                    if item.is_dir():
                        # Thư mục
                        analysis_data["file_tree"].append({
                            "type": "directory",
                            "name": item.name,
                            "path": str(item_rel_path),
                            "depth": depth
                        })
                        
                        # Thêm vào project structure (chỉ 3 level đầu)
                        if depth <= 3:
                            analysis_data["project_structure"][str(item_rel_path)] = {
                                "type": "directory",
                                "path": str(item_rel_path)
                            }
                        
                        # Đệ quy vào thư mục con
                        scan_directory(item, item_rel_path, depth + 1)
                        
                    else:
                        # File
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
                            file_info = {
                                "type": "file",
                                "name": item.name,
                                "path": str(item_rel_path),
                                "size_bytes": file_size,
                                "size_human": format_size(file_size),
                                "extension": ext,
                                "depth": depth
                            }
                            analysis_data["file_tree"].append(file_info)
                            
                            # PHÂN LOẠI FILE
                            file_path_str = str(item_rel_path).lower()
                            
                            # Backend files
                            if any(pattern in file_path_str for pattern in 
                                  ['/api/', '/routes/', '/controllers/', '/models/', 
                                   '/schemas/', '/crud/', '/services/', '/app.py', 
                                   'main.py', 'server.py', 'index.py']):
                                analysis_data["backend_files"][str(item_rel_path)] = {
                                    "size": file_size,
                                    "type": ext,
                                    "priority": "high" if is_high_priority_file(item_rel_path) else "normal"
                                }
                            
                            # Frontend files
                            elif any(pattern in file_path_str for pattern in 
                                    ['/components/', '/pages/', '/views/', '/layouts/',
                                     'app.js', 'app.ts', 'app.jsx', 'app.tsx', 
                                     'index.js', 'index.ts', 'index.jsx', 'index.tsx']):
                                analysis_data["frontend_files"][str(item_rel_path)] = {
                                    "size": file_size,
                                    "type": ext,
                                    "priority": "high" if is_high_priority_file(item_rel_path) else "normal"
                                }
                            
                            # Config files
                            if any(pattern in file_path_str for pattern in 
                                  ['package.json', 'requirements.txt', 'dockerfile', 
                                   'docker-compose.yml', 'composer.json', 'pom.xml',
                                   'build.gradle', 'gradle.properties', 'webpack.config',
                                   'vite.config', 'next.config', 'nuxt.config', 
                                   'tailwind.config', 'postcss.config', 'tsconfig.json',
                                   '.eslintrc', '.prettierrc', 'babel.config']):
                                analysis_data["config_files"][str(item_rel_path)] = {
                                    "size": file_size,
                                    "type": ext
                                }
                            
                            # Build files
                            if any(pattern in file_path_str for pattern in 
                                  ['makefile', 'cmakelists.txt', 'build.xml', 
                                   'gruntfile.js', 'gulpfile.js']):
                                analysis_data["build_files"][str(item_rel_path)] = {
                                    "size": file_size,
                                    "type": ext
                                }
                            
                            # Đọc nội dung file quan trọng
                            should_read_content = (
                                (ext in CODE_EXTENSIONS and 
                                 not any(ignore in item.name.lower() for ignore in IGNORE_CONTENT_FILES)) or
                                is_high_priority_file(item_rel_path) or
                                is_key_file(item.name, ext, str(item_rel_path))
                            )
                            
                            if should_read_content and file_size < 50000:  # 50KB limit
                                read_file_content(item, item_rel_path, file_size, ext)
                                
                        except (OSError, PermissionError) as e:
                            print(f"⚠️ Lỗi đọc file {item_rel_path}: {e}")
                            continue
                            
                except (PermissionError, OSError):
                    continue
                    
        except PermissionError as e:
            print(f"⚠️ Không có quyền truy cập thư mục: {relative_path}")
        except Exception as e:
            print(f"⚠️ Lỗi không xác định khi quét {relative_path}: {e}")
    
    def read_file_content(file_path, rel_path, file_size, extension):
        """Đọc nội dung file"""
        try:
            content = None
            encodings = ['utf-8', 'latin-1', 'cp1252', 'utf-16', 'ascii']
            
            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding, errors='ignore') as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue
            
            if content is not None:
                # Giới hạn nội dung để tránh file quá lớn
                max_chars = 30000
                if len(content) > max_chars:
                    content = content[:max_chars] + f"\n\n... [TRUNCATED, TOTAL: {len(content)} characters]"
                
                analysis_data["file_contents"][str(rel_path)] = {
                    "size": file_size,
                    "lines": len(content.splitlines()),
                    "content": content,
                    "encoding": encoding
                }
                
                # PHÂN TÍCH API ENDPOINTS cho file Python
                if extension == '.py' and ('/api/' in str(rel_path) or '/routes/' in str(rel_path)):
                    extract_api_endpoints(str(rel_path), content)
                
                # Đánh dấu file quan trọng
                if is_key_file(file_path.name, extension, str(rel_path)):
                    analysis_data["key_files"][str(rel_path)] = {
                        "type": get_file_type(file_path.name, extension),
                        "description": get_file_description(file_path.name, extension, str(rel_path)),
                        "priority": "high" if is_high_priority_file(rel_path) else "normal",
                        "lines": len(content.splitlines())
                    }
                    
        except Exception as e:
            analysis_data["file_contents"][str(rel_path)] = {
                "error": f"Cannot read file: {str(e)}"
            }
    
    def extract_api_endpoints(file_path, content):
        """Trích xuất thông tin API endpoints từ file Python"""
        endpoints = []
        lines = content.split('\n')
        
        # Mở rộng pattern matching cho các framework
        patterns = [
            '@router.', '@app.route', '@blueprint.route', '@api.route',
            'fastapi.', 'flask_restful.', 'django.urls.path'
        ]
        
        for i, line in enumerate(lines):
            line = line.strip()
            
            # Tìm các route decorators
            if any(pattern in line for pattern in patterns):
                endpoint_info = {
                    "file": file_path,
                    "line": i + 1,
                    "method": extract_http_method(line),
                    "path": extract_path(line),
                    "function": extract_function_name(lines, i)
                }
                endpoints.append(endpoint_info)
        
        if endpoints:
            analysis_data["api_endpoints"][file_path] = endpoints
    
    def extract_http_method(line):
        """Trích xuất HTTP method từ decorator"""
        line_lower = line.lower()
        if 'get' in line_lower: return 'GET'
        if 'post' in line_lower: return 'POST'
        if 'put' in line_lower: return 'PUT'
        if 'delete' in line_lower: return 'DELETE'
        if 'patch' in line_lower: return 'PATCH'
        if 'options' in line_lower: return 'OPTIONS'
        if 'head' in line_lower: return 'HEAD'
        return 'UNKNOWN'
    
    def extract_path(line):
        """Trích xuất path từ decorator"""
        # Tìm path trong dấu nháy
        matches = re.findall(r'["\']([^"\']*)["\']', line)
        if matches:
            return matches[0]
        # Tìm path trong dấu ngoặc
        matches = re.findall(r'\(([^)]*)\)', line)
        if matches:
            return matches[0].strip(" '\"")
        return 'UNKNOWN'
    
    def extract_function_name(lines, start_index):
        """Trích xuất tên function từ decorator"""
        for i in range(start_index + 1, min(start_index + 10, len(lines))):
            line = lines[i].strip()
            if line.startswith('def '):
                match = line.split('def ')[1].split('(')[0].strip()
                return match
            if line.startswith('async def '):
                match = line.split('async def ')[1].split('(')[0].strip()
                return match
        return 'UNKNOWN'
    
    def is_key_file(filename, extension, file_path):
        """Xác định file quan trọng"""
        filename_lower = filename.lower()
        file_path_lower = file_path.lower()
        
        key_filenames = {
            'package.json', 'requirements.txt', 'dockerfile', 'docker-compose.yml',
            'readme.md', 'makefile', '.gitignore', 'env.example', 'config.json',
            'settings.py', 'app.py', 'main.py', 'index.js', 'server.js',
            'webpack.config.js', 'tsconfig.json', 'pom.xml', 'build.gradle',
            'next.config.js', 'vite.config.js', 'tailwind.config.js',
            'layout.tsx', 'page.tsx', '_app.tsx', '_document.tsx',
            'config.py', 'models.py', 'schemas.py', 'crud.py', 'auth.py',
            'products.py', 'users.py', 'categories.py', 'composer.json',
            'gemfile', 'cargo.toml', 'go.mod', 'build.xml', 'gradlew',
            'nuxt.config.js', 'vue.config.js', 'angular.json', '.env.example'
        }
        
        # Check by filename
        if filename_lower in key_filenames:
            return True
        
        # Check by path patterns
        key_patterns = [
            '/config/', '/settings/', '/.config/', '/.settings/',
            '/src/main/', '/src/app/', '/app/', '/lib/', '/bin/',
            '/scripts/', '/tools/', '/utils/', '/helpers/'
        ]
        
        return any(pattern in file_path_lower for pattern in key_patterns)
    
    def get_file_type(filename, extension):
        """Xác định loại file"""
        config_files = {'.json', '.yaml', '.yml', '.config', '.conf', '.ini', '.toml'}
        code_files = {'.py', '.js', '.ts', '.java', '.cpp', '.c', '.php', '.rb', '.go', '.rs', '.dart'}
        web_files = {'.html', '.htm', '.css', '.scss', '.less', '.jsx', '.tsx', '.vue', '.svelte'}
        style_files = {'.css', '.scss', '.less', '.sass', '.styl'}
        document_files = {'.md', '.txt', '.rst', '.pdf', '.doc', '.docx'}
        
        if extension in config_files:
            return "config"
        elif extension in code_files:
            return "code"
        elif extension in web_files:
            return "web"
        elif extension in style_files:
            return "style"
        elif extension in document_files:
            return "documentation"
        elif extension == '.sql':
            return "database"
        else:
            return "other"
    
    def get_file_description(filename, extension, file_path):
        """Mô tả file"""
        descriptions = {
            'package.json': 'Node.js project configuration and dependencies',
            'requirements.txt': 'Python dependencies list',
            'dockerfile': 'Docker container configuration',
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
            'composer.json': 'PHP dependencies',
            'gemfile': 'Ruby dependencies',
            'go.mod': 'Go modules configuration',
            'cargo.toml': 'Rust dependencies'
        }
        
        file_path_lower = file_path.lower()
        filename_lower = filename.lower()
        
        # Mô tả dựa trên đường dẫn
        path_descriptions = {
            '/api/': 'API endpoints',
            '/routes/': 'Application routes',
            '/controllers/': 'MVC controllers',
            '/models/': 'Database models',
            '/schemas/': 'Data schemas',
            '/services/': 'Business logic',
            '/components/': 'UI components',
            '/pages/': 'Page components',
            '/views/': 'View templates',
            '/layouts/': 'Layout components',
            '/hooks/': 'React hooks',
            '/contexts/': 'React contexts',
            '/store/': 'State management',
            '/utils/': 'Utility functions',
            '/helpers/': 'Helper functions',
            '/config/': 'Configuration files',
            '/static/': 'Static assets',
            '/public/': 'Public files'
        }
        
        for pattern, desc in path_descriptions.items():
            if pattern in file_path_lower:
                return f"{desc} - {filename}"
        
        return descriptions.get(filename_lower, f"{extension or 'Unknown'} file")
    
    # Bắt đầu quét
    print("📊 Bắt đầu quét dự án...")
    scan_directory(start_path)
    
    # Tạo file đầu ra với tên cố định
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 1. File JSON đầy đủ
    json_file = output_dir / f"project_analysis_{timestamp}.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(analysis_data, f, indent=2, ensure_ascii=False)
    
    # 2. File tree text
    tree_file = output_dir / f"project_tree_{timestamp}.txt"
    with open(tree_file, 'w', encoding='utf-8') as f:
        f.write(generate_text_tree(analysis_data))
    
    # 3. File summary cho AI
    summary_file = output_dir / f"ai_summary_{timestamp}.md"
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write(generate_ai_summary(analysis_data))
    
    # 4. Tạo symlink cho file mới nhất
    try:
        for file_type, ext in [("project_analysis", ".json"), ("project_tree", ".txt"), ("ai_summary", ".md")]:
            latest_file = output_dir / f"{file_type}_latest{ext}"
            current_file = output_dir / f"{file_type}_{timestamp}{ext}"
            if latest_file.exists():
                latest_file.unlink()
            latest_file.symlink_to(current_file.name)
    except Exception as e:
        print(f"⚠️ Không thể tạo symlink: {e}")
    
    print(f"\n✅ ĐÃ TẠO GÓI PHÂN TÍCH HOÀN CHỈNH:")
    print(f"   📊 {json_file.name} - Dữ liệu đầy đủ (JSON)")
    print(f"   🌳 {tree_file.name} - Cây thư mục (Text)")
    print(f"   🤖 {summary_file.name} - Tóm tắt cho AI (Markdown)")
    print(f"   📁 Tổng files: {analysis_data['metadata']['total_files']}")
    print(f"   📦 Tổng kích thước: {format_size(analysis_data['metadata']['total_size_bytes'])}")
    print(f"   🐍 Backend files: {len(analysis_data['backend_files'])}")
    print(f"   ⚛️ Frontend files: {len(analysis_data['frontend_files'])}")
    print(f"   ⚙️ Config files: {len(analysis_data['config_files'])}")
    print(f"   🔗 API endpoints: {sum(len(v) for v in analysis_data['api_endpoints'].values())}")
    
    return {
        "json_file": json_file,
        "tree_file": tree_file,
        "summary_file": summary_file
    }

def generate_text_tree(analysis_data):
    """Tạo cây thư mục dạng text"""
    lines = [f"# PROJECT TREE ANALYSIS", ""]
    lines.append(f"Project: {analysis_data['metadata']['project_path']}")
    lines.append(f"Date: {analysis_data['metadata']['analysis_date']}")
    lines.append(f"Total Files: {analysis_data['metadata']['total_files']}")
    lines.append(f"Total Size: {format_size(analysis_data['metadata']['total_size_bytes'])}")
    lines.append(f"Scan Mode: {analysis_data['metadata']['scan_mode']}")
    lines.append("")
    lines.append("## FILE TREE")
    lines.append("")
    
    for item in analysis_data["file_tree"]:
        indent = "    " * item["depth"]
        if item["type"] == "directory":
            lines.append(f"{indent}📁 {item['name']}/")
        else:
            # Xác định icon dựa trên loại file
            ext = item.get('extension', '')
            if ext in ['.py']:
                icon = "🐍"
            elif ext in ['.js', '.ts', '.jsx', '.tsx']:
                icon = "⚛️"
            elif ext in ['.html', '.css', '.scss']:
                icon = "🌐"
            elif ext in ['.json', '.yaml', '.yml']:
                icon = "⚙️"
            elif ext in ['.md', '.txt']:
                icon = "📝"
            else:
                icon = "📄"
            
            # Kiểm tra xem có phải file quan trọng không
            is_key = str(item['path']) in analysis_data.get('key_files', {})
            key_marker = " 🔑" if is_key else ""
            
            lines.append(f"{indent}{icon} {item['name']} ({item.get('size_human', '0B')}){key_marker}")
    
    lines.append("")
    lines.append("## FILE TYPE STATISTICS")
    for ext, count in sorted(analysis_data["file_types"].items(), key=lambda x: x[1], reverse=True):
        if analysis_data["metadata"]["total_files"] > 0:
            percentage = (count / analysis_data["metadata"]["total_files"]) * 100
            lines.append(f"- {ext}: {count} files ({percentage:.1f}%)")
        else:
            lines.append(f"- {ext}: {count} files")
    
    # Thêm thông tin chi tiết
    lines.append("")
    lines.append("## PROJECT BREAKDOWN")
    lines.append(f"- Backend files: {len(analysis_data.get('backend_files', {}))}")
    lines.append(f"- Frontend files: {len(analysis_data.get('frontend_files', {}))}")
    lines.append(f"- Config files: {len(analysis_data.get('config_files', {}))}")
    lines.append(f"- Key files: {len(analysis_data.get('key_files', {}))}")
    
    return "\n".join(lines)

def generate_ai_summary(analysis_data):
    """Tạo tóm tắt cho AI"""
    lines = ["# AI ANALYSIS SUMMARY", ""]
    
    lines.append("## PROJECT OVERVIEW")
    lines.append(f"- **Path**: `{analysis_data['metadata']['project_path']}`")
    lines.append(f"- **Total Files**: {analysis_data['metadata']['total_files']}")
    lines.append(f"- **Total Size**: {format_size(analysis_data['metadata']['total_size_bytes'])}")
    lines.append(f"- **Scan Mode**: {analysis_data['metadata']['scan_mode']}")
    lines.append(f"- **Analysis Date**: {analysis_data['metadata']['analysis_date']}")
    lines.append("")
    
    lines.append("## PROJECT STRUCTURE")
    project_structure = analysis_data.get("project_structure", {})
    if project_structure:
        for path, info in list(project_structure.items())[:50]:  # Tăng lên 50 items
            lines.append(f"- `{path}` ({info.get('type', 'unknown')})")
    else:
        lines.append("- No project structure data available")
    lines.append("")
    
    lines.append("## KEY FILES IDENTIFIED")
    key_files = list(analysis_data.get("key_files", {}).items())
    if key_files:
        for path, info in key_files[:30]:  # Hiển thị 30 file quan trọng
            priority_icon = "🔴" if info.get('priority') == 'high' else "🟡"
            lines.append(f"- `{path}` - {info.get('type', 'unknown')} - {info.get('description', '')} {priority_icon}")
    else:
        lines.append("- No key files identified")
    lines.append("")
    
    lines.append("## FILE TYPE DISTRIBUTION")
    file_types = analysis_data.get("file_types", {})
    if file_types:
        total_files = analysis_data['metadata']['total_files']
        for ext, count in sorted(file_types.items(), key=lambda x: x[1], reverse=True)[:20]:
            if total_files > 0:
                percentage = (count / total_files) * 100
                lines.append(f"- `{ext}`: {count} files ({percentage:.1f}%)")
            else:
                lines.append(f"- `{ext}`: {count} files")
    else:
        lines.append("- No file type data available")
    lines.append("")
    
    lines.append("## API ENDPOINTS FOUND")
    api_endpoints = analysis_data.get("api_endpoints", {})
    if api_endpoints:
        total_endpoints = 0
        for file_path, endpoints in api_endpoints.items():
            lines.append(f"- `{file_path}`: {len(endpoints)} endpoints")
            total_endpoints += len(endpoints)
            for endpoint in endpoints[:5]:  # Hiển thị 5 endpoints đầu tiên mỗi file
                lines.append(f"  - {endpoint.get('method', 'UNKNOWN')} {endpoint.get('path', 'UNKNOWN')} -> {endpoint.get('function', 'UNKNOWN')}")
        lines.append(f"**Total API Endpoints**: {total_endpoints}")
    else:
        lines.append("- No API endpoints identified")
    lines.append("")
    
    lines.append("## BACKEND/FONTEND BREAKDOWN")
    lines.append(f"- **Backend Files**: {len(analysis_data.get('backend_files', {}))}")
    lines.append(f"- **Frontend Files**: {len(analysis_data.get('frontend_files', {}))}")
    lines.append("")
    
    lines.append("## AVAILABLE FILE CONTENTS")
    content_files = [(path, info) for path, info in analysis_data.get("file_contents", {}).items() 
                     if "content" in info]
    if content_files:
        lines.append(f"The following {len(content_files)} files have their content available for analysis:")
        for path, info in content_files[:30]:  # Hiển thị 30 file có nội dung
            lines.append(f"- `{path}` ({info.get('lines', 0)} lines, {info.get('size', 0)} bytes)")
    else:
        lines.append("- No file contents available")
    
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser(
        description='Tạo gói phân tích dự án cho AI - QUÉT MỌI LOẠI DỰ ÁN'
    )
    parser.add_argument(
        'path', 
        nargs='?', 
        default=os.getcwd(),  # Mặc định là thư mục hiện tại
        help='Đường dẫn dự án cần phân tích (mặc định: thư mục hiện tại)'
    )
    parser.add_argument(
        '-o', '--output', 
        default='ai_analysis', 
        help='Thư mục xuất kết quả (mặc định: ai_analysis)'
    )
    parser.add_argument(
        '-q', '--quiet',
        action='store_true',
        help='Chạy ở chế độ im lặng (chỉ hiển thị lỗi)'
    )
    
    args = parser.parse_args()
    
    if not args.quiet:
        print("🚀 TẠO GÓI PHÂN TÍCH DỰ ÁN HOÀN CHỈNH CHO AI")
        print("=" * 60)
        print("📝 Mỗi lần chạy sẽ tạo file mới với timestamp")
        print("💾 File mới nhất được link qua symlink *_latest.*")
        print("🌐 Hỗ trợ mọi loại dự án: Python, Node.js, Java, Go, Rust, v.v.")
        print("🔍 Tự động phát hiện Backend, Frontend, API endpoints")
        print("=" * 60)
    
    # Kiểm tra đường dẫn
    if not Path(args.path).exists():
        print(f"❌ Lỗi: Đường dẫn không tồn tại: {args.path}")
        print(f"📌 Thử dùng: python {sys.argv[0]} /đường/dẫn/đến/dự án")
        sys.exit(1)
    
    if not Path(args.path).is_dir():
        print(f"❌ Lỗi: Đường dẫn không phải là thư mục: {args.path}")
        sys.exit(1)
    
    try:
        result_files = generate_ai_analysis_package(args.path, args.output)
        
        if not args.quiet:
            print(f"\n📤 GỬI CHO AI:")
            print("1. Gửi file ai_summary_latest.md để có cái nhìn tổng quan")
            print("2. Gửi file project_analysis_latest.json nếu cần phân tích chi tiết")
            print("3. Gửi file project_tree_latest.txt để xem cấu trúc cây")
            print(f"\n📁 Files được lưu tại: {args.output}")
            print("📋 File mới nhất được đánh dấu bằng '_latest'")
    
    except KeyboardInterrupt:
        print("\n⚠️ Quá trình bị dừng bởi người dùng")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Lỗi không mong muốn: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()