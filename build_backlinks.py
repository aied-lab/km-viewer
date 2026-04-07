import os, re

KB = '/sessions/modest-dreamy-feynman/mnt/ATD-IIIEDU/knowledge-base'

mds = {f: open(os.path.join(KB, f), encoding='utf-8').read()
       for f in os.listdir(KB) if f.endswith('.md')}

names = {f: f[:-3] for f in mds}

# 掃描正向連結
forward = {f: re.findall(r'\[\[([^\]]+)\]\]', content) for f, content in mds.items()}

# 建立反向連結表
backlinks = {f: [] for f in mds}
for src, links in forward.items():
    for link in links:
        target = link + '.md'
        if target in mds and target != src:
            if names[src] not in backlinks[target]:
                backlinks[target].append(names[src])

# 更新每個 md，加入反向連結區塊
SECTION = '## 🔗 反向連結（Backlinks）'

for f, content in mds.items():
    bl = backlinks[f]

    # 移除舊的反向連結區塊
    content = re.sub(r'\n---\n## 🔗 反向連結.*', '', content, flags=re.DOTALL).rstrip()

    # 加入新的反向連結區塊
    if bl:
        bl_text = '\n'.join([f'- [[{name}]]' for name in bl])
        content += f'\n\n---\n{SECTION}\n\n{bl_text}\n'
    else:
        content += f'\n\n---\n{SECTION}\n\n（無）\n'

    with open(os.path.join(KB, f), 'w', encoding='utf-8') as fp:
        fp.write(content)
    print(f'✅ 更新：{f}  ← {bl if bl else "無"}')

print('\n完成！')
