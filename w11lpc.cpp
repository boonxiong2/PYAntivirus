// _Win11LPC 解释器 v0.1
// 作者: _Windows11   用 C艹 写自己的语言!

#include <iostream>
#include <fstream>
#include <string>
#include <vector>
#include <sstream>
using namespace std;

// ========== 第一步: 词法分析(tokenize) ==========
// 输入: "输出 1 + 2"
// 输出: {"输出", "1", "+", "2"}
vector<string> tokenize(const string& line) {
    vector<string> tokens;
    // TODO: 你来写!
    // 提示: 遍历每个字符, 遇到空格就切一刀
    //       遇到引号要把引号里的东西当整体
    return tokens;
}

// ========== 第二步: 执行(evaluate) ==========
void evaluate(const vector<string>& tokens) {
    if (tokens.empty()) return;
    
    // TODO: 你来写!
    // 如果 tokens[0] == "输出" -> 打印后面的东西
    // 如果是数字 -> 直接输出
}

// ========== 主程序 ==========
int main(int argc, char* argv[]) {
    if (argc < 2) {
        cerr << "用法: w11lpc <文件.w11>" << endl;
        return 1;
    }
    
    ifstream file(argv[1]);
    if (!file) {
        cerr << "打不开 " << argv[1] << endl;
        return 1;
    }
    
    string line;
    while (getline(file, line)) {
        if (line.empty()) continue;
        auto tokens = tokenize(line);
        evaluate(tokens);
    }
    
    return 0;
}
