/* M307 diagnostic (D63), opt-in, never part of the suite. On SIGSEGV at CPython 3.11.2's free_keys_object loop
   (Debian /usr/bin/python3.11, non-PIE, fault at 0x515ee3 "call *0x30(%rax)"), print the attribute names of the
   instance __dict__ being freed and the one whose value was already freed.

   Register meaning at 0x515ee3 (from the disassembly kept in the M307 evidence):
     r14 = PyDictKeysObject being freed (unicode keys, combined table)
     rbp = entry pointer, ALREADY advanced by 0x10: the entry being cleared is at rbp - 0x10 (me_key, me_value)
     rdi = the value whose refcount reached 0 (its type object is the freed memory)
     rbx = index of the next entry, r15 = dk_nentries
   Only reads memory; every pointer is checked against /proc/self/maps-free heuristics (alignment, type ==
   &PyUnicode_Type) before a string is printed. Build: gcc -shared -fPIC -o segv_dictkey.so segv_dictkey.c -ldl */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <ucontext.h>
#include <unistd.h>

static void *unicode_type;
static void *type_type;
static void put(const char *s) { write(2, s, strlen(s)); }

static int readable(const void *p, size_t n) {
    /* write() into a pipe fails with EFAULT instead of faulting when the memory is unmapped */
    static int fds[2] = {-1, -1};
    if (fds[0] < 0 && pipe(fds) != 0) return 0;
    if ((uintptr_t)p < 0x10000 || ((uintptr_t)p & 7)) return 0;
    char sink[64];
    if (n > sizeof sink) n = sizeof sink;
    if (write(fds[1], p, n) != (ssize_t)n) return 0;
    return read(fds[0], sink, n) == (ssize_t)n;
}

/* CPython 3.11 PyASCIIObject: refcnt, type, length, hash, state(4), pad(4), wstr -> data at 48 (compact ascii) */
static int name_of(const void *obj, char *out, size_t cap) {
    if (!readable(obj, 48)) return 0;
    const uintptr_t *w = obj;
    if ((void *)w[1] != unicode_type) return 0;
    long len = (long)w[2];
    uint32_t state = *(const uint32_t *)((const char *)obj + 32);
    int compact = (state >> 5) & 1, ascii = (state >> 6) & 1;
    if (!compact || !ascii || len <= 0 || len > 120) return 0;
    const char *data = (const char *)obj + 48;
    if (!readable(data, (size_t)len)) return 0;
    size_t n = (size_t)len < cap - 1 ? (size_t)len : cap - 1;
    memcpy(out, data, n);
    out[n] = 0;
    return 1;
}

static const char *type_name(const void *obj, char *out, size_t cap) {
    if (!readable(obj, 16)) return "(unreadable object)";
    const uintptr_t *w = obj;
    const void *tp = (const void *)w[1];
    if (!readable(tp, 32)) return "(unreadable type)";
    const char *name = (const char *)((const uintptr_t *)tp)[3];          /* tp_name at offset 0x18 */
    if (!readable(name, 8)) return "(unreadable tp_name)";
    size_t i = 0;
    for (; i < cap - 1 && readable(name + i, 1) && name[i] && name[i] >= 32 && name[i] < 127; i++) out[i] = name[i];
    out[i] = 0;
    return out;
}

static void handler(int sig, siginfo_t *si, void *vctx) {
    ucontext_t *uc = (ucontext_t *)vctx;
    greg_t *g = uc->uc_mcontext.gregs;
    char buf[512], key[128], tn[128];
    uintptr_t rip = (uintptr_t)g[REG_RIP], rsp0 = 0;
    if (readable((void *)g[REG_RSP], 8)) rsp0 = *(uintptr_t *)g[REG_RSP];
    snprintf(buf, sizeof buf, "\n=== native SIGSEGV (segv_dictkey) fault %p RIP %p [rsp] %p ===\n", si->si_addr,
             (void *)rip, (void *)rsp0);
    put(buf);
    /* The faulting call is either at 0x515ee3 (NULL type slot) or one frame in (jumped to a garbage address). */
    if (rip != 0x515ee3 && rsp0 != 0x515ee6) {
        put("not the free_keys_object site; no dict decoding\n");
    } else {
        uintptr_t rbp = (uintptr_t)g[REG_RBP], r14 = (uintptr_t)g[REG_R14];
        long rbx = (long)g[REG_RBX], r15 = (long)g[REG_R15];
        snprintf(buf, sizeof buf, "keys=%p entry_index=%ld of nentries=%ld value=%p\n", (void *)r14, rbx - 1, r15,
                 (void *)g[REG_RDI]);
        put(buf);
        const uintptr_t *entry = (const uintptr_t *)(rbp - 0x10);
        if (readable(entry, 16) && name_of((void *)entry[0], key, sizeof key)) {
            snprintf(buf, sizeof buf, "FREED VALUE IS ATTRIBUTE: '%s'\n", key);
        } else {
            snprintf(buf, sizeof buf, "freed value's key unreadable (%p)\n", readable(entry, 8) ? (void *)entry[0] : 0);
        }
        put(buf);
        if (readable((void *)r14, 0x20)) {
            unsigned log2_index_bytes = *(const unsigned char *)(r14 + 9);
            const uintptr_t *first = (const uintptr_t *)(r14 + 0x20 + ((uintptr_t)1 << log2_index_bytes));
            for (long i = 0; i < r15 && i < 400; i++) {
                const uintptr_t *e = first + 2 * i;
                if (!readable(e, 16)) break;
                if (!name_of((void *)e[0], key, sizeof key)) snprintf(key, sizeof key, "?%p", (void *)e[0]);
                const char *state = i < rbx - 1 ? "cleared" : i == rbx - 1 ? "FREED" : "pending";
                const char *t = (i >= rbx && e[1]) ? type_name((void *)e[1], tn, sizeof tn) : "";
                snprintf(buf, sizeof buf, "  [%ld] %-7s %s %s\n", i, state, key, t);
                put(buf);
            }
        }
    }
    signal(sig, SIG_DFL);
    raise(sig);
}

__attribute__((constructor)) static void install(void) {
    static char stack[1 << 17];
    unicode_type = dlsym(RTLD_DEFAULT, "PyUnicode_Type");
    type_type = dlsym(RTLD_DEFAULT, "PyType_Type");
    stack_t ss = {.ss_sp = stack, .ss_size = sizeof stack, .ss_flags = 0};
    sigaltstack(&ss, 0);
    struct sigaction sa;
    memset(&sa, 0, sizeof sa);
    sa.sa_sigaction = handler;
    sa.sa_flags = SA_SIGINFO | SA_ONSTACK;
    sigaction(SIGSEGV, &sa, 0);
}
