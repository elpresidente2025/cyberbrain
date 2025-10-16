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
print('Creating backup: ' + backup_path)
with open(file_path, 'rb') as f:
    with open(backup_path, 'wb') as backup:
        backup.write(f.read())

# UTF-8로 읽기 시도 (여러 인코딩 시도)
encodings = ['utf-8', 'cp949', 'euc-kr', 'utf-8-sig', 'latin1']
content = None

for encoding in encodings:
    try:
        print('Trying encoding: ' + encoding)
        with codecs.open(file_path, 'r', encoding=encoding, errors='replace') as f:
            content = f.read()
        print('SUCCESS with: ' + encoding)
        break
    except Exception as e:
        print('FAILED with: ' + encoding + ' - ' + str(e))
        continue

if content is None:
    print('ERROR: All encoding attempts failed')
    exit(1)

# UTF-8로 저장
print('Saving as UTF-8...')
with codecs.open(file_path, 'w', encoding='utf-8', errors='replace') as f:
    f.write(content)

print('COMPLETE!')
print('Original backup: ' + backup_path)
print('Fixed file: ' + file_path)
