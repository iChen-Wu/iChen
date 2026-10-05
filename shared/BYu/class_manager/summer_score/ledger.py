"""台账读写（存储新格式）"""
import json
from GYun.data.client import GyunClient
from BYu.class_manager.summer_score.config import generate_group_map_from_list

def _fetch_all_entities(client: GyunClient) -> list:
    """循环获取全部实体（处理分页）"""
    all_entities = []
    page = 1
    page_size = 100
    while True:
        try:
            res = client.query_entities({}, page=page, page_size=page_size)
        except Exception:
            break
        if not isinstance(res, dict):
            break
        items = res.get('list', [])
        if not items:
            break
        all_entities.extend(items)
        total = res.get('total', 0)
        if len(all_entities) >= total:
            break
        page += 1
    return all_entities

def load_score_ledger(client: GyunClient) -> dict:
    """加载所有学生台账，自动将旧布尔值转换为扣分值"""
    entities = _fetch_all_entities(client)
    ledger = {}
    for entity in entities:
        if entity.get('type') != 'student_ledger':
            continue
        content = entity.get('content', '')
        if not content:
            continue
        try:
            data = json.loads(content)
        except:
            continue
        name = data.get('name')
        records = data.get('records', [])
        if not name:
            continue

        # ---- 兼容旧数据：将布尔值转换为扣分值 ----
        for rec in records:
            if 'morning_chain' in rec and isinstance(rec['morning_chain'], bool):
                # 旧格式：True=完成=扣0, False=未完成=扣1
                rec['morning_chain_deduct'] = 0 if rec['morning_chain'] else 1
                rec['afternoon_chain_deduct'] = 0 if rec.get('afternoon_chain', True) else 1
                rec['morning_checkin_deduct'] = 0 if rec.get('morning_checkin', True) else 1
                rec['afternoon_checkin_deduct'] = 0 if rec.get('afternoon_checkin', True) else 1
                # 删除旧字段
                del rec['morning_chain']
                if 'afternoon_chain' in rec:
                    del rec['afternoon_chain']
                if 'morning_checkin' in rec:
                    del rec['morning_checkin']
                if 'afternoon_checkin' in rec:
                    del rec['afternoon_checkin']
                # 重新计算attendance_deduct
                rec['attendance_deduct'] = (
                    rec['morning_chain_deduct'] +
                    rec['afternoon_chain_deduct'] +
                    rec['morning_checkin_deduct'] +
                    rec['afternoon_checkin_deduct']
                )
                rec['homework_deduct'] = len(rec.get('missing_subjects', []))
                if rec.get('is_leave', False):
                    rec['final_score'] = 0
                else:
                    rec['final_score'] = -(rec['attendance_deduct'] + rec['homework_deduct']) + rec.get('homework_bonus', 0) + rec.get('morning_early_bonus', 0)

        eid = entity.get('entity_id')
        ledger[name] = {'eid': eid, 'records': records}
    return ledger

def save_score_ledger(ledger: dict, client: GyunClient) -> None:
    """保存台账：title 存姓名标识，content 存完整数据"""
    saved_count = 0
    for name, info in ledger.items():
        records = info['records']
        content = json.dumps({'name': name, 'records': records}, ensure_ascii=False)
        eid = info.get('eid')
        if eid:
            try:
                client.update_entity(eid, {
                    'content': content,
                    'title': f'积分台账-{name}'
                })
            except Exception as e:
                print(f"更新 {name} 失败: {e}，尝试创建新实体")
                try:
                    eid = client.create_entity({
                        'type': 'student_ledger',
                        'title': f'积分台账-{name}',
                        'content': content,
                        'tags': ['student_ledger', '积分台账']
                    })
                    info['eid'] = eid
                    print(f"  创建新实体成功，eid={eid}")
                except Exception as ce:
                    print(f"  创建实体也失败: {ce}")
                    continue
        else:
            try:
                eid = client.create_entity({
                    'type': 'student_ledger',
                    'title': f'积分台账-{name}',
                    'content': content,
                    'tags': ['student_ledger', '积分台账']
                })
                info['eid'] = eid
                print(f"创建学生 {name} 实体成功，eid={eid}")
            except Exception as e:
                print(f"创建学生 {name} 实体失败: {e}")
                continue
        saved_count += 1
    print(f"✅ 台账保存完成：成功 {saved_count}/{len(ledger)} 名学生记录。")

def get_student_day_record(ledger: dict, name: str, date: str) -> dict | None:
    if name not in ledger:
        return None
    for rec in ledger[name]['records']:
        if rec['date'] == date:
            return rec
    return None

def update_student_ledger(ledger: dict, name: str, day_record: dict) -> None:
    """更新或覆盖指定学生当天的记录"""
    if name not in ledger:
        ledger[name] = {'eid': None, 'records': []}
    records = ledger[name]['records']
    for i, rec in enumerate(records):
        if rec['date'] == day_record['date']:
            records[i] = day_record
            return
    records.append(day_record)

def load_student_group_map(client: GyunClient) -> dict:
    """从 config 实体的 content 读取分组映射"""
    entities = _fetch_all_entities(client)
    for entity in entities:
        if entity.get('type') != 'config':
            continue
        content = entity.get('content', '')
        if content:
            try:
                data = json.loads(content)
                if 'student_group_map' in data:
                    return data['student_group_map']
            except:
                pass
        if entity.get('title') == '学生分组映射':
            val = entity.get('value') or entity.get('extra', {}).get('value')
            if val:
                if isinstance(val, str):
                    try:
                        return json.loads(val)
                    except:
                        pass
                elif isinstance(val, dict):
                    return val
    # 如果不存在则自动生成并保存
    group_map = generate_group_map_from_list()
    save_student_group_map(client, group_map)
    return group_map

def save_student_group_map(client: GyunClient, group_map: dict) -> None:
    """保存分组映射到 content"""
    content = json.dumps({'student_group_map': group_map}, ensure_ascii=False)
    entities = _fetch_all_entities(client)
    existing_eid = None
    for entity in entities:
        if entity.get('type') == 'config' and entity.get('title') == '学生分组映射':
            existing_eid = entity.get('entity_id')
            break
    if existing_eid:
        try:
            client.update_entity(existing_eid, {
                'content': content,
                'title': '学生分组映射'
            })
            print("分组映射更新成功。")
        except Exception as e:
            print(f"更新分组映射失败: {e}")
    else:
        try:
            eid = client.create_entity({
                'type': 'config',
                'title': '学生分组映射',
                'content': content,
                'tags': ['config', '积分台账']
            })
            print(f"分组映射创建成功，eid={eid}")
        except Exception as e:
            print(f"创建分组映射失败: {e}")