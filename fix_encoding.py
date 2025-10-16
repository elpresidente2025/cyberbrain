# -*- coding: utf-8 -*-
"""
posts.js 파일의 인코딩 문제를 수정하는 스크립트
"""

import os
import codecs

# 파일 경로
file_path = r'E:\ai-secretary\functions\handlers\posts.js'
backup_path = r'E:\ai-secretary\functions\handlers\posts.js.backup'

# 백업 생성
print(f'백업 생성: {backup_path}')
with open(file_path, 'rb') as f:
    with open(backup_path, 'wb') as backup:
        backup.write(f.read())

# UTF-8로 읽기 시도 (여러 인코딩 시도)
encodings = ['utf-8', 'cp949', 'euc-kr', 'utf-8-sig', 'latin1']
content = None

for encoding in encodings:
    try:
        print(f'시도: {encoding} 인코딩으로 읽기...')
        with codecs.open(file_path, 'r', encoding=encoding, errors='replace') as f:
            content = f.read()
        print(f'✅ 성공: {encoding}')
        break
    except Exception as e:
        print(f'❌ 실패: {encoding} - {e}')
        continue

if content is None:
    print('❌ 모든 인코딩 시도 실패')
    exit(1)

# UTF-8로 저장
print('UTF-8로 저장 중...')
with codecs.open(file_path, 'w', encoding='utf-8', errors='replace') as f:
    f.write(content)

print('✅ 완료!')
print(f'원본 백업: {backup_path}')
print(f'수정된 파일: {file_path}')
