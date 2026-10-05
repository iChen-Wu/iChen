#!/usr/bin/env python3
# cli.py
# =============================================================================
# 模块：歌曲管理命令行界面
# =============================================================================
# 运行方式：
#   cd /path/to/project
#   python -m BYu.class_manager.song.cli
# =============================================================================

import json
import os
from typing import List, Dict

# ⭐ 包绝对导入
from BYu.class_manager.song.service import (
    add_songs_from_input,
    get_song_info,
    get_all_songs,
    set_song_weight,
    delete_song,
    restore_song,
    recognize_songs_from_images_service,
    get_statistics,
    normalize_recommender
)


# ============================================================
# CLI 类
# ============================================================

class SongCLI:
    """歌曲管理命令行界面"""

    def __init__(self):
        pass

    # ---- 界面辅助 ----

    def _print_banner(self):
        print("\n" + "=" * 70)
        print("  🎵 歌曲管理系统 V2.0")
        print("=" * 70)

    def _print_menu(self):
        print("\n" + "=" * 70)
        print("  1. 📋 查看所有歌曲")
        print("  2. ➕ 添加歌曲")
        print("  3. 🔍 查询单首歌曲")
        print("  4. ⚖️  修改歌曲权重")
        print("  5. 🗑️  删除歌曲")
        print("  6. 📊 统计信息")
        print("  7. 🔄 回溯歌曲（展示全部，批量选择）")
        print("  0. 🚪 退出")
        print("-" * 70)

    def _confirm(self, msg: str) -> bool:
        return input(f"{msg} (y/n): ").strip().lower() == 'y'

    def _wait_for_enter(self):
        input("\n按 Enter 继续...")

    def _parse_range(self, text: str, max_val: int) -> List[int]:
        """解析用户输入的编号范围，返回索引列表（0-based）"""
        indices = set()
        parts = text.split(',')

        for part in parts:
            part = part.strip()
            if '-' in part:
                try:
                    start, end = part.split('-')
                    start = int(start.strip()) - 1
                    end = int(end.strip()) - 1
                    for i in range(max(0, start), min(max_val, end + 1)):
                        indices.add(i)
                except ValueError:
                    continue
            else:
                try:
                    idx = int(part) - 1
                    if 0 <= idx < max_val:
                        indices.add(idx)
                except ValueError:
                    continue

        return sorted(indices)

    # ---- 1. 查看所有歌曲 ----

    def _list_songs(self):
        print("\n📋 正在获取歌单...")
        try:
            songs = get_all_songs()
            if not songs:
                print("📭 当前歌单为空")
                self._wait_for_enter()
                return

            songs.sort(key=lambda x: int(x.get('weight', 0)), reverse=True)

            print(f"\n📀 共 {len(songs)} 首歌曲:")
            print("-" * 85)
            print(f"  {'ID':<6} {'歌名':<16} {'歌手':<14} {'权重':<6} {'推荐人':<10} {'类型':<6}")
            print("-" * 85)

            for song in songs:
                sid = song.get('id', '')
                name = song.get('name', '')[:16]
                singer = song.get('singer', '')[:14]
                weight = song.get('weight', 0)
                recommender = song.get('tj_name', '') or song.get('tj', '') or '无'
                lx = song.get('lx_name', '') or song.get('lx', '') or '个人'
                weight_display = f"{weight} ⚠️" if weight == 0 else str(weight)
                print(f"  {sid:<6} {name:<16} {singer:<14} {weight_display:<6} {recommender:<10} {lx:<6}")

            print("-" * 85)
            inactive_count = sum(1 for s in songs if s.get('weight', 0) == 0)
            if inactive_count > 0:
                print(f"💡 权重为 0 的歌曲（{inactive_count} 首）已停用")

        except Exception as e:
            print(f"❌ 查询异常: {e}")

        self._wait_for_enter()

    # ---- 2. 添加歌曲 ----

    def _add_song(self):
        print("\n➕ 添加歌曲")
        print("-" * 40)
        print("  1. 手动输入（单首）")
        print("  2. 批量输入（多首）")
        print("  3. 📷 从图片导入")

        choice = input("请选择 (1/2/3): ").strip()
        if choice == "1":
            self._add_single()
        elif choice == "2":
            self._add_batch()
        elif choice == "3":
            self._add_from_images()
        else:
            print("❌ 无效选择")

        self._wait_for_enter()

    def _add_single(self):
        print("\n📝 单首歌曲录入")
        name = input("🎵 歌名: ").strip()
        if not name:
            print("❌ 歌名不能为空")
            return

        singer = input("🎤 歌手: ").strip()
        if not singer:
            print("❌ 歌手不能为空")
            return

        print("👤 推荐人（输入中文全名或缩写，如 张博宇 / ZBY）")
        recommender = input("推荐人: ").strip()
        if not recommender:
            print("❌ 推荐人不能为空")
            return

        lx = input("📂 类型 (班级/个人，默认个人): ").strip() or "个人"
        weight_str = input("⚖️ 权重 (默认5): ").strip()
        weight = int(weight_str) if weight_str.isdigit() else 5

        print("\n📋 即将添加:")
        print(f"  歌名: {name}")
        print(f"  歌手: {singer}")
        print(f"  推荐人: {recommender}")
        print(f"  类型: {lx}")
        print(f"  权重: {weight}")

        if not self._confirm("确认添加？"):
            print("已取消")
            return

        songs = [{"song": name, "singer": singer, "recommender": recommender, "type": lx, "weight": weight}]
        result = add_songs_from_input(songs)
        if result["success"]:
            print(f"✅ {result['message']}")
        else:
            print(f"❌ 添加失败: {result['message']}")
            error_details = result.get("error_details")
            if error_details:
                print("\n📋 失败详情:")
                for err in error_details:
                    print(f"  - {err}")

    def _add_batch(self):
        print("\n📝 批量录入（每行一首，格式: 歌名, 歌手, 推荐人, 类型, 权重）")
        print("   示例: 稻香, 周杰伦, ZBY, 班级, 10")
        print("   输入空行结束")

        songs = []
        while True:
            line = input("> ").strip()
            if not line:
                break
            parts = [p.strip() for p in line.split(',')]
            if len(parts) < 3:
                print("  ⚠️ 格式错误（至少需要: 歌名, 歌手, 推荐人），跳过")
                continue
            songs.append({
                "song": parts[0],
                "singer": parts[1],
                "recommender": parts[2],
                "type": parts[3] if len(parts) > 3 else "个人",
                "weight": int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 5
            })

        if not songs:
            print("❌ 未输入有效歌曲")
            return

        print(f"\n📋 即将添加 {len(songs)} 首歌曲:")
        for s in songs:
            print(f"  - {s['song']} / {s['singer']} (推荐: {s['recommender']}, 权重: {s['weight']})")

        if not self._confirm("确认添加？"):
            print("已取消")
            return

        result = add_songs_from_input(songs)
        if result["success"]:
            print(f"✅ {result['message']}")
        else:
            print(f"❌ 添加失败: {result['message']}")

    def _edit_song_list(self, songs: List[Dict]) -> List[Dict]:
        """
        交互式编辑歌曲列表，返回修改后的列表
        支持：修改单首、统一设置推荐人/类型/权重
        """
        while True:
            print("\n✏️ 编辑模式")
            print("  输入编号 (如 2) 修改该首歌曲")
            print("  输入 'all' 统一设置所有歌曲的推荐人/类型/权重")
            print("  输入 'done' 完成编辑")
            print("-" * 50)

            # 显示当前列表
            print(f"  {'编号':<4} {'歌名':<16} {'歌手':<14} {'推荐人':<10} {'类型':<6} {'权重':<6}")
            print("-" * 50)
            for i, s in enumerate(songs, 1):
                name = s.get('name', '')[:16]
                singer = s.get('singer', '')[:14]
                rec = s.get('recommender', '') or '无'
                lx = s.get('type', '个人') or '个人'
                weight = s.get('weight', 5)
                print(f"  {i:<4} {name:<16} {singer:<14} {rec:<10} {lx:<6} {weight:<6}")
            print("-" * 50)

            cmd = input("请输入命令: ").strip().lower()
            if cmd == 'done':
                break
            elif cmd == 'all':
                new_rec = input("统一推荐人 (缩写或中文全名，回车不修改): ").strip()
                new_type = input("统一类型 (班级/个人，回车不修改): ").strip()
                new_weight_str = input("统一权重 (数字，回车不修改): ").strip()
                new_weight = int(new_weight_str) if new_weight_str.isdigit() else None

                for s in songs:
                    if new_rec:
                        s['recommender'] = new_rec
                    if new_type in ['班级', '个人']:
                        s['type'] = new_type
                    if new_weight is not None:
                        s['weight'] = new_weight
                print("✅ 已应用统一设置")
            elif cmd.isdigit():
                idx = int(cmd) - 1
                if 0 <= idx < len(songs):
                    s = songs[idx]
                    print(f"\n修改第 {idx+1} 首: {s.get('name')} - {s.get('singer')}")
                    new_name = input(f"  歌名 [{s.get('name')}]: ").strip()
                    if new_name:
                        s['name'] = new_name
                    new_singer = input(f"  歌手 [{s.get('singer')}]: ").strip()
                    if new_singer:
                        s['singer'] = new_singer
                    new_rec = input(f"  推荐人 [{s.get('recommender', '')}]: ").strip()
                    if new_rec:
                        s['recommender'] = new_rec
                    new_type = input(f"  类型 [{s.get('type', '个人')}]: ").strip()
                    if new_type in ['班级', '个人']:
                        s['type'] = new_type
                    new_weight_str = input(f"  权重 [{s.get('weight', 5)}]: ").strip()
                    if new_weight_str.isdigit():
                        s['weight'] = int(new_weight_str)
                    print("✅ 已更新")
                else:
                    print("❌ 无效编号")
            else:
                print("❌ 无效命令，请输入编号、'all' 或 'done'")

        return songs

    def _add_from_images(self):
        print("\n📷 从图片导入歌曲")
        paths_input = input("图片路径（多个用空格分隔）: ").strip()
        if not paths_input:
            print("❌ 未输入路径")
            return

        paths = [p.strip() for p in paths_input.split() if os.path.exists(p.strip())]
        if not paths:
            print("❌ 没有有效的图片文件")
            return

        print(f"⏳ 正在识别 {len(paths)} 张图片...")
        grouped_songs = recognize_songs_from_images_service(paths, verbose=False)

        total_uploaded = 0
        total_skipped = 0

        for idx, songs in enumerate(grouped_songs, 1):
            img_path = paths[idx - 1]
            print(f"\n{'='*60}")
            print(f"📸 图片 {idx}/{len(paths)}: {os.path.basename(img_path)}")
            print('='*60)

            if not songs:
                print("⚠️ 该图片未识别到任何歌曲，跳过")
                total_skipped += 1
                continue

            # 显示识别到的歌曲列表
            print(f"\n📋 识别到 {len(songs)} 首歌曲:")
            print("-" * 70)
            print(f"  {'编号':<4} {'歌名':<16} {'歌手':<14} {'推荐人':<10} {'类型':<6} {'权重':<6}")
            print("-" * 70)
            for i, s in enumerate(songs, 1):
                name = s.get('name', '')[:16]
                singer = s.get('singer', '')[:14]
                recommender = s.get('recommender', '') or '无'
                lx = s.get('type', '个人') or '个人'
                weight = s.get('weight', 5)
                print(f"  {i:<4} {name:<16} {singer:<14} {recommender:<10} {lx:<6} {weight:<6}")
            print("-" * 70)

            # ---- 操作选项 ----
            print("\n选项:")
            print("  [1] 上传此列表（推荐人自动转为缩写）")
            print("  [2] 编辑此列表后再上传")
            print("  [3] 跳过此列表")
            choice = input("请选择 (1/2/3): ").strip()

            if choice == "3":
                print("⏭️ 跳过此列表")
                total_skipped += 1
                continue

            # ---- 编辑模式 ----
            if choice == "2":
                songs = self._edit_song_list(songs)
                if not songs:
                    print("⏭️ 列表为空，跳过")
                    total_skipped += 1
                    continue

            # ---- 统一推荐人检测 ----
            recommenders = [s.get('recommender', '').strip() for s in songs if s.get('recommender', '').strip()]
            if recommenders:
                unique_recs = set(recommenders)
                if len(unique_recs) == 1:
                    default_rec = list(unique_recs)[0]
                    print(f"\n💡 检测到统一推荐人: {default_rec}")
                    if self._confirm("是否使用此推荐人作为所有歌曲的推荐人？"):
                        for s in songs:
                            s['recommender'] = default_rec
                else:
                    if self._confirm("检测到多个不同推荐人，是否统一设置为某个推荐人？"):
                        new_rec = input("请输入统一推荐人 (缩写或中文全名): ").strip()
                        if new_rec:
                            for s in songs:
                                s['recommender'] = new_rec

            # ---- 转换为缩写显示预览 ----
            display_songs = []
            for s in songs:
                rec = normalize_recommender(s.get('recommender', ''))
                display_songs.append({
                    'name': s.get('name'),
                    'singer': s.get('singer'),
                    'recommender': rec,
                    'type': s.get('type', '个人'),
                    'weight': s.get('weight', 5)
                })

            print("\n📋 最终确认列表（推荐人已转为缩写）:")
            print("-" * 70)
            print(f"  {'编号':<4} {'歌名':<16} {'歌手':<14} {'推荐人':<10} {'类型':<6} {'权重':<6}")
            print("-" * 70)
            for i, s in enumerate(display_songs, 1):
                name = s.get('name', '')[:16]
                singer = s.get('singer', '')[:14]
                rec = s.get('recommender', '') or '无'
                lx = s.get('type', '个人') or '个人'
                weight = s.get('weight', 5)
                print(f"  {i:<4} {name:<16} {singer:<14} {rec:<10} {lx:<6} {weight:<6}")
            print("-" * 70)

            if not self._confirm("确认上传此列表？"):
                print("⏭️ 跳过此列表")
                total_skipped += 1
                continue

            # ---- 上传 ----
            songs_to_add = []
            for s in display_songs:
                songs_to_add.append({
                    "song": s['name'],
                    "singer": s['singer'],
                    "recommender": s['recommender'],
                    "type": s['type'],
                    "weight": s['weight']
                })

            result = add_songs_from_input(songs_to_add)
            if result["success"]:
                print(f"✅ {result['message']}")
                total_uploaded += len(songs_to_add)
            else:
                print(f"❌ 上传失败: {result['message']}")
                if result.get("error_details"):
                    print("\n📋 失败详情:")
                    for err in result["error_details"]:
                        print(f"  - {err}")

        print(f"\n✅ 导入完成: 成功上传 {total_uploaded} 首，跳过 {total_skipped} 个列表")
        self._wait_for_enter()

    # ---- 3. 查询单首歌曲 ----

    def _get_song(self):
        print("\n🔍 查询单首歌曲")
        print("-" * 40)

        name = input("🎵 请输入歌名关键词: ").strip()
        if not name:
            print("❌ 歌名不能为空")
            self._wait_for_enter()
            return

        all_songs = get_all_songs()
        if not all_songs:
            print("❌ 无法获取歌单")
            self._wait_for_enter()
            return

        matched = []
        for s in all_songs:
            song_name = s.get('name', '')
            if name.lower() in song_name.lower():
                matched.append(s)

        if not matched:
            print(f"❌ 未找到包含 '{name}' 的歌曲")
            self._wait_for_enter()
            return

        print(f"\n📋 找到 {len(matched)} 首匹配歌曲:")
        print("-" * 85)
        print(f"  {'编号':<4} {'ID':<6} {'歌名':<16} {'歌手':<14} {'权重':<6} {'推荐人':<10} {'类型':<6}")
        print("-" * 85)

        for idx, s in enumerate(matched, 1):
            sid = s.get('id', '')
            song_name = s.get('name', '')[:16]
            singer = s.get('singer', '')[:14]
            weight = s.get('weight', 0)
            recommender = s.get('tj_name', '') or s.get('tj', '') or '无'
            lx = s.get('lx_name', '') or s.get('lx', '') or '个人'
            print(f"  {idx:<4} {sid:<6} {song_name:<16} {singer:<14} {weight:<6} {recommender:<10} {lx:<6}")
        print("-" * 85)

        if len(matched) == 1:
            choice = "1"
            print("✅ 只有一首匹配，自动选中")
        else:
            choice = input(f"请选择编号 (1-{len(matched)}): ").strip()

        try:
            idx = int(choice) - 1
            if idx < 0 or idx >= len(matched):
                print("❌ 无效编号")
                self._wait_for_enter()
                return
            selected = matched[idx]
        except ValueError:
            print("❌ 请输入有效数字")
            self._wait_for_enter()
            return

        data = selected
        print("\n📀 歌曲详情:")
        print("-" * 40)
        print(f"  ID        : {data.get('id')}")
        print(f"  歌名      : {data.get('name')}")
        print(f"  歌手      : {data.get('singer')}")
        print(f"  推荐人    : {data.get('tj_name', '') or data.get('tj', '无')}")
        print(f"  类型      : {data.get('lx_name', '') or data.get('lx', '')}")
        print(f"  权重      : {data.get('weight')}")
        print(f"  播放链接  : {data.get('play_url') or '无'}")
        print("-" * 40)

        self._wait_for_enter()

    # ---- 4. 修改权重 ----

    def _set_weight(self):
        print("\n⚖️ 修改歌曲权重")
        print("-" * 40)

        name = input("🎵 请输入歌名关键词: ").strip()
        if not name:
            print("❌ 歌名不能为空")
            self._wait_for_enter()
            return

        all_songs = get_all_songs()
        if not all_songs:
            print("❌ 无法获取歌单")
            self._wait_for_enter()
            return

        matched = []
        for s in all_songs:
            song_name = s.get('name', '')
            if name.lower() in song_name.lower():
                matched.append(s)

        if not matched:
            print(f"❌ 未找到包含 '{name}' 的歌曲")
            self._wait_for_enter()
            return

        print(f"\n📋 找到 {len(matched)} 首匹配歌曲:")
        print("-" * 85)
        print(f"  {'编号':<4} {'ID':<6} {'歌名':<16} {'歌手':<14} {'当前权重':<8} {'推荐人':<10}")
        print("-" * 85)

        for idx, s in enumerate(matched, 1):
            sid = s.get('id', '')
            song_name = s.get('name', '')[:16]
            singer = s.get('singer', '')[:14]
            weight = s.get('weight', 0)
            recommender = s.get('tj_name', '') or s.get('tj', '') or '无'
            print(f"  {idx:<4} {sid:<6} {song_name:<16} {singer:<14} {weight:<8} {recommender:<10}")
        print("-" * 85)

        if len(matched) == 1:
            choice = "1"
            print("✅ 只有一首匹配，自动选中")
        else:
            choice = input(f"请选择编号 (1-{len(matched)}): ").strip()

        try:
            idx = int(choice) - 1
            if idx < 0 or idx >= len(matched):
                print("❌ 无效编号")
                self._wait_for_enter()
                return
            selected = matched[idx]
        except ValueError:
            print("❌ 请输入有效数字")
            self._wait_for_enter()
            return

        song_id = selected.get('id')
        song_name = selected.get('name')
        song_singer = selected.get('singer')
        current_weight = selected.get('weight', 0)

        print(f"\n📌 选中: {song_name} - {song_singer} (ID={song_id})")
        print(f"📌 当前权重: {current_weight}")

        weight_str = input("⚖️ 请输入新权重: ").strip()
        if not weight_str or not weight_str.isdigit():
            print("❌ 请输入有效数字")
            self._wait_for_enter()
            return

        new_weight = int(weight_str)
        if not self._confirm(f"将权重从 {current_weight} 改为 {new_weight}？"):
            print("已取消")
            self._wait_for_enter()
            return

        result = set_song_weight(song_id, new_weight)
        if result["success"]:
            print(f"✅ {result['message']}")
        else:
            print(f"❌ 修改失败: {result['message']}")

        self._wait_for_enter()

    # ---- 5. 删除歌曲 ----

    def _delete_song(self):
        print("\n🗑️ 删除歌曲")
        print("⚠️ 此操作不可逆！")
        print("-" * 40)

        name = input("🎵 请输入歌名关键词: ").strip()
        if not name:
            print("❌ 歌名不能为空")
            self._wait_for_enter()
            return

        all_songs = get_all_songs()
        if not all_songs:
            print("❌ 无法获取歌单")
            self._wait_for_enter()
            return

        matched = []
        for s in all_songs:
            song_name = s.get('name', '')
            if name.lower() in song_name.lower():
                matched.append(s)

        if not matched:
            print(f"❌ 未找到包含 '{name}' 的歌曲")
            self._wait_for_enter()
            return

        print(f"\n📋 找到 {len(matched)} 首匹配歌曲:")
        print("-" * 85)
        print(f"  {'编号':<4} {'ID':<6} {'歌名':<16} {'歌手':<14} {'权重':<6} {'推荐人':<10}")
        print("-" * 85)

        for idx, s in enumerate(matched, 1):
            sid = s.get('id', '')
            song_name = s.get('name', '')[:16]
            singer = s.get('singer', '')[:14]
            weight = s.get('weight', 0)
            recommender = s.get('tj_name', '') or s.get('tj', '') or '无'
            print(f"  {idx:<4} {sid:<6} {song_name:<16} {singer:<14} {weight:<6} {recommender:<10}")
        print("-" * 85)

        if len(matched) == 1:
            choice = "1"
            print("✅ 只有一首匹配，自动选中")
        else:
            choice = input(f"请选择编号 (1-{len(matched)}): ").strip()

        try:
            idx = int(choice) - 1
            if idx < 0 or idx >= len(matched):
                print("❌ 无效编号")
                self._wait_for_enter()
                return
            selected = matched[idx]
        except ValueError:
            print("❌ 请输入有效数字")
            self._wait_for_enter()
            return

        song_name = selected.get('name')
        song_singer = selected.get('singer')
        song_id = selected.get('id')
        current_weight = selected.get('weight', 0)

        print(f"\n📌 即将删除: {song_name} - {song_singer} (ID={song_id}, 权重={current_weight})")
        if not self._confirm("⚠️ 确认删除？此操作不可逆！"):
            print("已取消")
            self._wait_for_enter()
            return

        result = delete_song(song_name, song_singer)
        if result["success"]:
            print(f"✅ {result['message']}")
        else:
            print(f"❌ 删除失败: {result['message']}")

        self._wait_for_enter()

    # ---- 6. 统计信息 ----

    def _show_statistics(self):
        print("\n📊 统计信息")
        try:
            stats = get_statistics()
            print("-" * 40)
            print(f"  总歌曲数: {stats['total']}")
            print(f"  活跃歌曲 (权重>0): {stats['active_count']}")
            print(f"  最高权重: {stats['max_weight']}")

            if stats['top_songs']:
                print("\n  🏆 权重 Top 5:")
                for s in stats['top_songs']:
                    print(f"    - {s.get('name')} / {s.get('singer')} (权重: {s.get('weight')})")

            if stats['recommender_stats']:
                print("\n  👤 推荐人排行:")
                for recommender, count in stats['recommender_stats'][:10]:
                    print(f"    - {recommender}: {count} 首")

            print("-" * 40)
        except Exception as e:
            print(f"❌ 统计失败: {e}")

        self._wait_for_enter()

    # ---- 7. 回溯歌曲 ----

    def _restore_song(self):
        print("\n🔄 回溯歌曲（删除 + 重新上传）")
        print("💡 回溯后歌曲将获得新 ID，相当于从未播放过")
        print("💡 支持批量选择，输入编号如: 1,3,5 或 1-5")
        print("-" * 40)

        all_songs = get_all_songs()
        if not all_songs:
            print("📭 当前歌单为空，无需回溯")
            self._wait_for_enter()
            return

        # 按权重升序（停用的排在前面）
        all_songs.sort(key=lambda x: int(x.get('weight', 0)))

        print(f"\n📋 当前歌单共 {len(all_songs)} 首歌曲:")
        print("-" * 85)
        print(f"  {'编号':<4} {'ID':<6} {'歌名':<16} {'歌手':<14} {'权重':<6} {'推荐人':<10} {'类型':<6}")
        print("-" * 85)

        for idx, s in enumerate(all_songs, 1):
            sid = s.get('id', '')
            song_name = s.get('name', '')[:16]
            singer = s.get('singer', '')[:14]
            weight = s.get('weight', 0)
            recommender = s.get('tj_name', '') or s.get('tj', '') or '无'
            lx = s.get('lx_name', '') or s.get('lx', '') or '个人'
            weight_display = f"{weight} ⚠️" if weight == 0 else str(weight)
            print(f"  {idx:<4} {sid:<6} {song_name:<16} {singer:<14} {weight_display:<6} {recommender:<10} {lx:<6}")
        print("-" * 85)

        inactive_count = sum(1 for s in all_songs if s.get('weight', 0) == 0)
        if inactive_count > 0:
            print(f"💡 权重为 0 的歌曲（{inactive_count} 首）已停用，适合回溯")

        choice_str = input(f"\n请选择编号（支持 1,3,5 或 1-5，回车取消）: ").strip()
        if not choice_str:
            print("已取消")
            self._wait_for_enter()
            return

        selected_indices = self._parse_range(choice_str, len(all_songs))
        if not selected_indices:
            print("❌ 无效的编号选择")
            self._wait_for_enter()
            return

        selected_songs = [all_songs[i] for i in selected_indices]

        print(f"\n📌 选中 {len(selected_songs)} 首歌曲:")
        for s in selected_songs:
            weight = s.get('weight', 0)
            status = "🔄 停用" if weight == 0 else f"权重 {weight}"
            print(f"  - {s.get('name')} / {s.get('singer')} ({status})")

        if not self._confirm(f"\n确认对 {len(selected_songs)} 首歌曲执行回溯（删除+重新上传）？"):
            print("已取消")
            self._wait_for_enter()
            return

        success_count = 0
        fail_count = 0

        for s in selected_songs:
            song_name = s.get('name')
            song_singer = s.get('singer')
            current_weight = s.get('weight', 0)
            recommender = s.get('tj_name', '') or s.get('tj', '')
            lx = s.get('lx_name', '') or s.get('lx', '') or '班级'
            new_weight = current_weight if current_weight > 0 else 5

            print(f"\n🔄 处理: {song_name} - {song_singer}")

            del_result = delete_song(song_name, song_singer)
            if not del_result["success"]:
                print(f"  ❌ 删除失败: {del_result.get('message')}")
                fail_count += 1
                continue
            print("  ✅ 删除成功")

            songs = [{
                "song": song_name,
                "singer": song_singer,
                "recommender": recommender if recommender else "ZBY",
                "type": lx,
                "weight": new_weight
            }]
            result = add_songs_from_input(songs)
            if result["success"]:
                print(f"  ✅ 重新添加成功 (权重: {new_weight})")
                success_count += 1
            else:
                print(f"  ❌ 重新添加失败: {result.get('message')}")
                fail_count += 1

        print(f"\n✅ 回溯完成: 成功 {success_count} 首，失败 {fail_count} 首")
        self._wait_for_enter()

    # ---- 主循环 ----

    def run(self):
        self._print_banner()
        while True:
            self._print_menu()
            choice = input("\n请选择操作: ").strip()

            if choice == "0":
                print("\n👋 再见！")
                break
            elif choice == "1":
                self._list_songs()
            elif choice == "2":
                self._add_song()
            elif choice == "3":
                self._get_song()
            elif choice == "4":
                self._set_weight()
            elif choice == "5":
                self._delete_song()
            elif choice == "6":
                self._show_statistics()
            elif choice == "7":
                self._restore_song()
            else:
                print("❌ 无效选择，请重新输入")


# ============================================================
# 主入口
# ============================================================

if __name__ == "__main__":
    cli = SongCLI()
    try:
        cli.run()
    except KeyboardInterrupt:
        print("\n\n👋 已退出")
        import sys
        sys.exit(0)