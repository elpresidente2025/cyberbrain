import os
import re

# 17 files list
files = [
    r"E:\ai-secretary\frontend\src\components\ProfileRequiredRoute.jsx",
    r"E:\ai-secretary\frontend\src\components\loading\BaseSpinner.jsx",
    r"E:\ai-secretary\frontend\src\components\PostViewerModal.jsx",
    r"E:\ai-secretary\frontend\src\components\MaintenancePage.jsx",
    r"E:\ai-secretary\frontend\src\components\generate\PreviewPane.jsx",
    r"E:\ai-secretary\frontend\src\components\generate\DraftGrid.jsx",
    r"E:\ai-secretary\frontend\src\components\onboarding\CongratulationsModal.jsx",
    r"E:\ai-secretary\frontend\src\components\onboarding\OnboardingWelcomeModal.jsx",
    r"E:\ai-secretary\frontend\src\components\onboarding\ProfileBioGuideModal.jsx",
    r"E:\ai-secretary\frontend\src\components\admin\UserManagement.jsx",
    r"E:\ai-secretary\frontend\src\components\admin\UserSearchModal.jsx",
    r"E:\ai-secretary\frontend\src\components\admin\PostSearchModal.jsx",
    r"E:\ai-secretary\frontend\src\components\admin\ErrorsMiniTable.jsx",
    r"E:\ai-secretary\frontend\src\components\admin\QuickActions.jsx",
    r"E:\ai-secretary\frontend\src\components\admin\StatusUpdateModal.jsx",
    r"E:\ai-secretary\frontend\src\components\admin\NoticeManager.jsx",
    r"E:\ai-secretary\frontend\src\components\admin\PerformanceMonitor.jsx",
]

for file_path in files:
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        continue

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Replace '{theme.palette.ui?.header || '#152484'}' with theme.palette.ui?.header || '#152484'
    content = content.replace("'{theme.palette.ui?.header || '#152484'}'", "theme.palette.ui?.header || '#152484'")

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"Fixed: {file_path}")

print("\nDone!")
