/* M264 diagnostic (D63): on SIGSEGV print the fault address, RIP and a heuristic stack scan of return addresses
   resolved with dladdr (no gdb in the sandbox; frames from a scan can include stale values). */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <ucontext.h>
#include <unistd.h>
static void put(const char *s) { write(2, s, strlen(s)); }
static void sym(const char *tag, void *p) {
    Dl_info di; char buf[512];
    if (dladdr(p, &di) && di.dli_fname) {
        snprintf(buf, sizeof buf, "%s %p %s(%s+0x%lx)\n", tag, p, di.dli_fname, di.dli_sname ? di.dli_sname : "?",
                 (unsigned long)((char *)p - (char *)(di.dli_sname ? di.dli_saddr : di.dli_fbase)));
    } else {
        snprintf(buf, sizeof buf, "%s %p (unmapped or anonymous)\n", tag, p);
    }
    put(buf);
}
static void handler(int sig, siginfo_t *si, void *vctx) {
    ucontext_t *uc = (ucontext_t *)vctx;
    void *rip = (void *)uc->uc_mcontext.gregs[REG_RIP];
    unsigned long *rsp = (unsigned long *)uc->uc_mcontext.gregs[REG_RSP];
    char buf[160];
    put("\n=== native SIGSEGV (segv_bt) ===\n");
    snprintf(buf, sizeof buf, "fault address %p\n", si->si_addr); put(buf);
    sym("RIP", rip);
    for (int i = 0; i < 4; i++) { snprintf(buf, sizeof buf, "rsp[%d]", i); sym(buf, (void *)rsp[i]); }
    int shown = 0;
    for (int i = 0; i < 6000 && shown < 45; i++) {
        Dl_info di;
        void *p = (void *)rsp[i];
        if ((unsigned long)p > 0x10000 && dladdr(p, &di) && di.dli_fname && di.dli_sname && !strstr(di.dli_sname, "_PyRuntime") && !strstr(di.dli_sname, "_Type") &&
            !strstr(di.dli_fname, "segv_bt")) {
            snprintf(buf, sizeof buf, "stack[%d]", i); sym(buf, p); shown++;
        }
    }
    signal(sig, SIG_DFL);
    raise(sig);
}
__attribute__((constructor)) static void install(void) {
    static char stack[1 << 16];
    stack_t ss = { .ss_sp = stack, .ss_size = sizeof stack, .ss_flags = 0 };
    sigaltstack(&ss, 0);
    struct sigaction sa; memset(&sa, 0, sizeof sa);
    sa.sa_sigaction = handler; sa.sa_flags = SA_SIGINFO | SA_ONSTACK;
    sigaction(SIGSEGV, &sa, 0);
}
