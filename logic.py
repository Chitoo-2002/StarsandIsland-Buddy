def calc_profits(crop_data, settings, custom_ferts):
    """
    核心收益计算函数 (V12.0 动态肥料版)
    """
    try:
        st = settings
        P = {}
        F = {}
        
        name = crop_data.get("name")
        is_t = crop_data.get("is_tree")
        qty = float(crop_data.get("h_qty", 1) or 1)
        cnt = int(crop_data.get("h_count", 1) or 1)
        raw_p = float(crop_data.get("raw_price", 0) or 0)
        seed = float(crop_data.get("seed_price", 0) or 0)
        
        t1 = float(crop_data.get("t1", 0) or 0)
        t2 = float(crop_data.get("t2", 0) or 0)
        t3 = float(crop_data.get("t3", 0) or 0)
        base_t = t1 + t2 + t3
        
        # ⚡ 核心变更：动态组装肥料列表 (格式：名称, 成本, 减时, 增产倍率)
        ferts = [("无肥料", 0, 0, 1.0)]
        for f in custom_ferts:
            f_name = f.get("name", "未知")
            f_cost = float(f.get("cost", 0))
            f_effect = float(f.get("effect", 0))
            
            if f.get("type") == "speed":
                ferts.append((f_name, f_cost, f_effect, 1.0))
            elif f.get("type") == "yield":
                ferts.append((f_name, f_cost, 0, f_effect))
            
        for fname, fcost, ftime, fmult in ferts:
            # A. 总产量逻辑
            if is_t:
                total_yield = qty * fmult 
                yield_logic_str = f"单次产量" if fmult==1 else "单次产量 × 肥料倍率"
                yield_val_str = f"{qty}" if fmult==1 else f"{qty} × {fmult}"
            else:
                total_yield = qty * cnt * fmult
                yield_logic_str = "单次产量 × 收获次数 × 肥料倍率"
                yield_val_str = f"{qty} × {cnt} × {fmult}"

            # B. 总成本逻辑
            if is_t:
                t_cost = fcost 
                cost_logic_str = "单次施肥成本" if fcost > 0 else "0"
                cost_val_str = f"{fcost}" if fcost > 0 else "0"
            else:
                t_cost = seed + fcost * cnt
                if fcost > 0:
                    cost_logic_str = "种子费 + (肥料单价 × 施肥次数)"
                    cost_val_str = f"{seed} + ({fcost} × {cnt})"
                else:
                    cost_logic_str = "种子费"
                    cost_val_str = f"{seed}"

            # C. 总时间逻辑
            if is_t:
                pure_t2 = max(float(crop_data.get("t2", 0) or 0.1), 0.1)
                t_time = max(pure_t2 - ftime, 0.1)
                if ftime > 0:
                    time_logic_str = "复果时间 - 肥料减时"
                    time_val_str = f"{pure_t2} - {ftime}"
                else:
                    time_logic_str = "复果时间"
                    time_val_str = f"{pure_t2}"
            else:
                t_time = max(base_t - ftime * cnt, 0.1)
                if ftime > 0:
                    time_logic_str = "基础生长时间 - (肥料减时/次 × 次数)"
                    time_val_str = f"{base_t} - ({ftime} × {cnt})"
                else:
                    time_logic_str = "基础生长时间"
                    time_val_str = f"{base_t}"

            # --- 策略计算 ---
            # 1. 直接出售
            if raw_p > 0:
                k = f"直接出售_{fname}"
                res = (total_yield * raw_p - t_cost) / t_time
                P[k] = res
                F[k] = {"title_n": "总收入 - 总成本", "str_n": f"({yield_logic_str}) × 直售单价 - ({cost_logic_str})", "val_n": f"({yield_val_str}) × {raw_p} - ({cost_val_str})", "title_d": "总耗时 (小时)", "str_d": time_logic_str, "val_d": time_val_str, "res": res}
            
            # 2. 一级加工
            ptype = crop_data.get("primary_type", "无")
            pqty = float(crop_data.get("primary_qty", 0) or 0)
            if ptype != "无" and pqty > 0:
                pk = {"面粉": "price_flour", "果肉": "price_pulp", "蔬菜汁": "price_juice", "糖": "price_sugar"}.get(ptype)
                if pk:
                    price = st[pk]
                    k = f"一级加工_{fname}"
                    res = (total_yield * pqty * price - t_cost) / t_time
                    P[k] = res
                    F[k] = {"title_n": f"总收入({ptype}) - 总成本", "str_n": f"(总产量 × {ptype}产出量 × {ptype}单价) - ({cost_logic_str})", "val_n": f"({total_yield:.1f} × {pqty} × {price}) - ({cost_val_str})", "title_d": "总耗时", "str_d": time_logic_str, "val_d": time_val_str, "res": res}

            # 3. 果酱
            if crop_data.get("can_jam"):
                jp = float(crop_data.get("jam_price", 0) or 0)
                jt = float(crop_data.get("jam_time", 0) or 0)
                if jp > 0:
                    k = f"果酱_{fname}"
                    bottles = total_yield / 2
                    net_income = bottles * (jp - st["sugar_cost"])
                    total_time_jam = t_time + bottles * jt
                    res = (net_income - t_cost) / total_time_jam
                    P[k] = res
                    F[k] = {"title_n": "净收入(扣除糖成本) - 种植成本", "str_n": f"((总产量÷2) × (果酱售价 - 糖成本)) - ({cost_logic_str})", "val_n": f"(({total_yield:.1f}÷2) × ({jp} - {st['sugar_cost']})) - ({cost_val_str})", "title_d": "种植时间 + 酿造时间", "str_d": f"{time_logic_str} + (瓶数 × 单瓶酿造时长)", "val_d": f"{t_time:.1f} + ({bottles:.1f} × {jt})", "res": res}

            # 4. 腌菜
            if crop_data.get("can_pickle"):
                pp = float(crop_data.get("pickle_price", 0) or 0)
                pt = float(crop_data.get("pickle_time", 0) or 0)
                if pp > 0:
                    k = f"腌菜_{fname}"
                    bottles = total_yield / 2
                    net_income = bottles * (pp - st["salt_cost"])
                    total_time_pickle = t_time + bottles * pt
                    res = (net_income - t_cost) / total_time_pickle
                    P[k] = res
                    F[k] = {"title_n": "净收入(扣除盐成本) - 种植成本", "str_n": f"((总产量÷2) × (腌菜售价 - 盐成本)) - ({cost_logic_str})", "val_n": f"(({total_yield:.1f}÷2) × ({pp} - {st['salt_cost']})) - ({cost_val_str})", "title_d": "种植时间 + 腌制时间", "str_d": f"{time_logic_str} + (瓶数 × 单瓶腌制时长)", "val_d": f"{t_time:.1f} + ({bottles:.1f} × {pt})", "res": res}

        return P, F
    except Exception as e:
        print(f"Calc Error: {e}")
        return {}, {}