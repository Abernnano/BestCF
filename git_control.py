#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Git版本控制工具
使用数字筛选菜单进行常见Git操作
"""

import subprocess
import os
import sys

def run_command(cmd, cwd=None):
    """执行命令并返回结果"""
    try:
        result = subprocess.run(
            cmd, 
            shell=True, 
            capture_output=True, 
            text=True, 
            cwd=cwd
        )
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return 1, "", str(e)

def print_menu():
    """打印菜单"""
    print("\n=== Git版本控制工具 ===")
    print("1. 查看当前状态")
    print("2. 添加所有更改")
    print("3. 提交更改")
    print("4. 推送到远程仓库")
    print("5. 从远程仓库拉取")
    print("6. 查看提交历史")
    print("7. 查看远程仓库信息")
    print("8. 退出")
    print("====================\n")

def get_user_input():
    """获取用户输入"""
    try:
        choice = int(input("请输入操作编号: "))
        return choice
    except ValueError:
        return 0

def main():
    """主函数"""
    # 确保在Git仓库目录中
    repo_path = os.path.dirname(os.path.abspath(__file__))
    
    # 检查是否在Git仓库中
    code, stdout, stderr = run_command("git rev-parse --is-inside-work-tree", cwd=repo_path)
    if code != 0:
        print("错误: 当前目录不是Git仓库!")
        print("1. 初始化新的Git仓库")
        print("2. 退出")
        try:
            choice = int(input("请选择操作: "))
            if choice == 1:
                # 初始化新的Git仓库
                print("正在初始化新的Git仓库...")
                code, stdout, stderr = run_command("git init", cwd=repo_path)
                if code == 0:
                    print("Git仓库初始化成功!")
                else:
                    print("初始化失败:", stderr)
                    sys.exit(1)
            else:
                sys.exit(1)
        except ValueError:
            sys.exit(1)
    
    while True:
        print_menu()
        choice = get_user_input()
        
        if choice == 1:
            # 查看当前状态
            print("\n=== 查看当前状态 ===")
            code, stdout, stderr = run_command("git status", cwd=repo_path)
            print(stdout)
            if stderr:
                print("错误:", stderr)
                
        elif choice == 2:
            # 添加所有更改
            print("\n=== 添加所有更改 ===")
            code, stdout, stderr = run_command("git add .", cwd=repo_path)
            if code == 0:
                print("已添加所有更改到暂存区")
            else:
                print("错误:", stderr)
                
        elif choice == 3:
            # 提交更改
            print("\n=== 提交更改 ===")
            commit_msg = input("请输入提交信息: ")
            code, stdout, stderr = run_command(f"git commit -m '{commit_msg}'", cwd=repo_path)
            if code == 0:
                print("提交成功!")
                print(stdout)
            else:
                print("错误:", stderr)
                
        elif choice == 4:
            # 推送到远程仓库
            print("\n=== 推送到远程仓库 ===")
            # 检查当前分支
            code, current_branch, stderr = run_command("git rev-parse --abbrev-ref HEAD", cwd=repo_path)
            current_branch = current_branch.strip()
            
            # 如果当前分支不是main，切换到main分支
            if current_branch != "main":
                print(f"当前分支是 {current_branch}，正在切换到 main 分支...")
                code, stdout, stderr = run_command("git checkout main", cwd=repo_path)
                if code != 0:
                    print("切换分支失败:", stderr)
                    input("\n按回车键继续...")
                    continue
                print("已切换到 main 分支")
            
            # 先从远程仓库拉取最新更改
            print("正在从远程仓库拉取最新更改...")
            code, stdout, stderr = run_command("git pull origin main --rebase", cwd=repo_path)
            if code != 0:
                print("拉取失败:", stderr)
                input("\n按回车键继续...")
                continue
            print("拉取成功")
            
            # 推送到main分支
            code, stdout, stderr = run_command("git push origin main", cwd=repo_path)
            if code == 0:
                print("推送成功!")
                print(stdout)
            else:
                print("错误:", stderr)
                
        elif choice == 5:
            # 从远程仓库拉取
            print("\n=== 从远程仓库拉取 ===")
            code, stdout, stderr = run_command("git pull", cwd=repo_path)
            if code == 0:
                print("拉取成功!")
                print(stdout)
            else:
                print("错误:", stderr)
                
        elif choice == 6:
            # 查看提交历史
            print("\n=== 查看提交历史 ===")
            code, stdout, stderr = run_command("git log --oneline -10", cwd=repo_path)
            print(stdout)
            if stderr:
                print("错误:", stderr)
                
        elif choice == 7:
            # 查看远程仓库信息
            print("\n=== 查看远程仓库信息 ===")
            code, stdout, stderr = run_command("git remote -v", cwd=repo_path)
            print(stdout)
            if stderr:
                print("错误:", stderr)
                
        elif choice == 8:
            # 退出
            print("\n退出Git版本控制工具，再见!")
            break
            
        else:
            print("\n无效的操作编号，请重新输入!")
        
        # 按回车键继续
        input("\n按回车键继续...")

if __name__ == "__main__":
    main()
