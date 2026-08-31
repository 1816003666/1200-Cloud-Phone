import os, pathlib
from dulwich import porcelain
root = pathlib.Path(r"C:\Users\熏香花朵凛然绽放\Desktop\1200台云手机部署\cloud-phone-board\cloud-phone-board")
r = porcelain.open_repo(str(root))
porcelain.add(r, ".")
# commit
cid = porcelain.commit(r, message="Initial commit: 1200 云手机批量管理平台（设备/脚本/文件/分组/任务/告警/看板）")
print("commit:", cid.decode()[:10])
# 设置 user 若未配置
# remote
remotes = list(porcelain.get_remotes(r).keys())
print("remotes:", remotes)
if b"origin" not in [x if isinstance(x,bytes) else x.encode() for x in remotes]:
    porcelain.remote_add(r, "origin", "https://github.com/1816003666/1200-Cloud-Phone.git")
    print("origin added")
print("token env:", "yes" if os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") else "no")
idx = r.open_index()
print("staged now:", len(list(idx.iteritems())))
