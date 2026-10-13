const TOKEN_URL = "/__girder_token";

const getProvider = () => window.trame?.refs?.girder_provider;

const getGirder = (provider) => provider?.$?.provides?.girder;
const clearGirderClient = (provider) => {
    const girder = getGirder(provider);
    if (!girder) return;

    girder.token.value = null;
    girder.rest.token = null;
    delete girder.rest._axios.defaults.headers.common["Girder-Token"];
    girder.user.value = null;

    provider.$emit("userLoggedOut");
};

const getSessionToken = async () => {
    const response = await fetch(TOKEN_URL, {
        cache: "no-store",
    });

    if (!response.ok) return null;

    return (await response.json()).token;
};
export const authenticateGirder = async () => {
    const provider = getProvider();
    const girder = getGirder(provider);
    if (!girder) {
        console.log("[medInriaWeb] Girder client not available");
        return;
    }

    try {
        const token = await getSessionToken();
        if (!token) {
            clearGirderClient(provider);
            return;
        }

        girder.token.value = token;
        girder.rest.token = token;
        girder.rest._axios.defaults.headers.common["Girder-Token"] = token;
        const { data: user } = await girder.rest.get("user/me");
        if (!user) {
            clearGirderClient(provider);
            return;
        }

        girder.user.value = user;
        provider.$emit("userFetched", { user, token });
    } catch (error) {
        console.error("[medInriaWeb] Automatic authentication failed:", error)
        clearGirderClient(provider);
    }
};

const syncGirderSession = async () => {
    const provider = getProvider();
    const girder = getGirder(provider);
    if (!girder) return;

    try {
        const token = await getSessionToken();
        if (token === girder.token.value) return;

        await authenticateGirder();
    } catch (error) {
        console.error("[medInriaWeb] Failed to synchronize Girder session:", error);
    }
};

document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
        syncGirderSession();
    }
});