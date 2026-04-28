/* $Header: /vobs/test_framework/include/test.h@@/main/rel3_feature/6 $ */
#ifndef FW_TEST_H
#define FW_TEST_H
#include "/view/fw_migration_view/vobs/shared_libs/include/fw_types.h"
#include <cstdio>
#include <functional>
#include <vector>
#include <string>
namespace fw { namespace test {
struct TestCase { std::string name; std::function<bool()> fn; };
class TestSuite {
public:
    void add(const std::string& name, std::function<bool()> fn) { m_cases.push_back({name, fn}); }
    int run() {
        int passed=0, failed=0;
        for (auto& tc : m_cases) {
            bool ok = tc.fn();
            printf("  [%s] %s\n", ok?"PASS":"FAIL", tc.name.c_str());
            ok ? ++passed : ++failed;
        }
        printf("Results: %d passed, %d failed\n", passed, failed);
        return failed;
    }
private:
    std::vector<TestCase> m_cases;
};
#define FW_ASSERT_EQ(a,b)  do { if ((a)!=(b)) { printf("ASSERT_EQ failed: %s != %s\n",#a,#b); return false; } } while(0)
#define FW_ASSERT_OK(s)    FW_ASSERT_EQ((s), fw::Status::OK)
}} // namespace fw::test
#endif
